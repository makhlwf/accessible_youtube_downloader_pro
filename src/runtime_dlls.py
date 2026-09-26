import os
import sys
from collections.abc import Iterable
from pathlib import Path

_dll_directory_handles = []
_registered_dll_directories: set[str] = set()


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
