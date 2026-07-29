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
