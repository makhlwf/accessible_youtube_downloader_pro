import mmap
import os
import struct
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_dll_directory_handles = []
_registered_dll_directories: set[str] = set()

# PE COFF machine identifiers we care about when validating bundled binaries.
IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_ARM64 = 0xAA64

_MACHINE_NAMES = {
    IMAGE_FILE_MACHINE_I386: "x86",
    IMAGE_FILE_MACHINE_AMD64: "x64",
    IMAGE_FILE_MACHINE_ARM64: "arm64",
}


def machine_name(machine: int | None) -> str:
    if not machine:
        return "unknown"
    return _MACHINE_NAMES.get(machine, hex(machine))


def pe_machine(path: Path | str) -> int | None:
    """Return the PE COFF machine value for ``path``, or ``None`` if not a PE.

    Reads only the DOS/PE headers, so it is cheap even for very large DLLs and
    safe to call on arbitrary files (non-PE input yields ``None``).
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(4096)
    except OSError:
        return None
    if len(header) < 0x40 or header[:2] != b"MZ":
        return None
    try:
        e_lfanew = struct.unpack_from("<I", header, 0x3C)[0]
        if e_lfanew + 6 > len(header) or header[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            return None
        return struct.unpack_from("<H", header, e_lfanew + 4)[0]
    except struct.error:
        return None


def pe_imported_dlls(path: Path | str) -> list[str]:
    """Return the names of the DLLs ``path`` imports at load time.

    Parses the PE import directory with the standard library only (no pefile
    dependency in the frozen app). Memory-maps the file so it stays cheap for
    the ~120 MB libmpv build. Returns ``[]`` for anything that is not a valid
    PE image or that cannot be parsed.
    """
    try:
        with open(path, "rb") as handle:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    except OSError, ValueError:
        return []

    try:
        data: Any = mapped
        if len(data) < 0x40 or data[:2] != b"MZ":
            return []
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            return []
        coff = e_lfanew + 4
        num_sections = struct.unpack_from("<H", data, coff + 2)[0]
        size_optional = struct.unpack_from("<H", data, coff + 16)[0]
        optional = coff + 20
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic == 0x20B:  # PE32+ (64-bit)
            num_rva = struct.unpack_from("<I", data, optional + 108)[0]
            directory_base = optional + 112
        elif magic == 0x10B:  # PE32 (32-bit)
            num_rva = struct.unpack_from("<I", data, optional + 92)[0]
            directory_base = optional + 96
        else:
            return []
        if num_rva < 2:  # need at least the import directory (index 1)
            return []
        import_rva = struct.unpack_from("<I", data, directory_base + 8)[0]
        if not import_rva:
            return []

        sections = []
        section_base = optional + size_optional
        for index in range(num_sections):
            offset = section_base + index * 40
            virtual_size = struct.unpack_from("<I", data, offset + 8)[0]
            virtual_addr = struct.unpack_from("<I", data, offset + 12)[0]
            raw_size = struct.unpack_from("<I", data, offset + 16)[0]
            raw_ptr = struct.unpack_from("<I", data, offset + 20)[0]
            sections.append((virtual_addr, max(virtual_size, raw_size), raw_ptr))

        def rva_to_offset(rva: int) -> int | None:
            for virtual_addr, span, raw_ptr in sections:
                if virtual_addr <= rva < virtual_addr + span:
                    return raw_ptr + (rva - virtual_addr)
            return None

        descriptor = rva_to_offset(import_rva)
        if descriptor is None:
            return []

        names: list[str] = []
        for index in range(1024):  # bound the loop against malformed tables
            entry = descriptor + index * 20
            if entry + 20 > len(data):
                break
            original_thunk = struct.unpack_from("<I", data, entry)[0]
            name_rva = struct.unpack_from("<I", data, entry + 12)[0]
            first_thunk = struct.unpack_from("<I", data, entry + 16)[0]
            if not (original_thunk or name_rva or first_thunk):
                break  # null terminator descriptor
            name_offset = rva_to_offset(name_rva) if name_rva else None
            if name_offset is not None and name_offset < len(data):
                end = data.find(b"\0", name_offset)
                if end != -1:
                    names.append(data[name_offset:end].decode("ascii", "replace"))
        return names
    except struct.error, ValueError:
        return []
    finally:
        mapped.close()


def _add_unique_path(paths: list[Path], path: Path) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if resolved.exists() and resolved not in paths:
        paths.append(resolved)


def runtime_roots(extra_roots: Iterable[Path | str] = ()) -> list[Path]:
    roots: list[Path] = []

    for root in extra_roots:
        _add_unique_path(roots, Path(root))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        _add_unique_path(roots, exe_dir)
        _add_unique_path(roots, exe_dir / "_internal")

    if hasattr(sys, "_MEIPASS"):
        _add_unique_path(roots, Path(sys._MEIPASS))  # type: ignore[attr-defined]

    _add_unique_path(roots, Path(__file__).resolve().parent)
    return roots


def configure_linux_display_backend() -> None:
    """Prefer XWayland for video embedding on Wayland sessions.

    mpv can only embed video into a foreign window through the ``wid`` option on
    X11, win32, and macOS (see ``src/include/mpv/client.h``). A native Wayland
    surface has no X11 window id to hand mpv, so embedded playback fails there
    while audio keeps working. When a Wayland session is detected we ask GDK to
    prefer the X11 backend (XWayland) so wx windows get a real X11 XID that mpv
    can embed into, with the native Wayland backend kept as a fallback so the app
    still launches (audio-only) if XWayland is unavailable.

    Must run before wx/GTK initializes (GDK reads ``GDK_BACKEND`` at startup); an
    explicit ``GDK_BACKEND`` set by the user is left untouched.
    """
    if not sys.platform.startswith("linux"):
        return
    if not os.environ.get("WAYLAND_DISPLAY"):
        return
    if os.environ.get("GDK_BACKEND"):
        return
    os.environ["GDK_BACKEND"] = "x11,wayland"


def configure_dll_search_path(extra_roots: Iterable[Path | str] = ()) -> list[Path]:
    roots = runtime_roots(extra_roots)
    if sys.platform != "win32":
        return roots

    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    known_entries = {entry.casefold() for entry in path_entries if entry}
    prepend_entries = [
        str(root) for root in roots if str(root).casefold() not in known_entries
    ]
    if prepend_entries:
        os.environ["PATH"] = os.pathsep.join(prepend_entries + path_entries)

    if hasattr(os, "add_dll_directory"):
        for root in roots:
            root_key = str(root).casefold()
            if root_key in _registered_dll_directories:
                continue
            try:
                handle = os.add_dll_directory(str(root))
            except OSError:
                continue
            _dll_directory_handles.append(handle)
            _registered_dll_directories.add(root_key)

    return roots
