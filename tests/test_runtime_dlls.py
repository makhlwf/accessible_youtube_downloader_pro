import os
import sys
from unittest.mock import MagicMock

import pytest

import runtime_dlls
from media_player import mpv_backend


@pytest.mark.parametrize("library", ["libmpv.so.2", "libmpv.so.1", None])
def test_linux_mpv_uses_system_library_without_dll_extraction(monkeypatch, library):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(mpv_backend, "_mpv_lib", None)
    discover = MagicMock(return_value=library)
    load = MagicMock(return_value=MagicMock())
    extract = MagicMock(side_effect=AssertionError("Windows extraction on Linux"))
    configure = MagicMock(side_effect=AssertionError("DLL search on Linux"))
    monkeypatch.setattr(mpv_backend, "find_library", discover)
    monkeypatch.setattr(mpv_backend.ctypes, "CDLL", load)
    monkeypatch.setattr(mpv_backend, "_mpv_candidates", extract)
    monkeypatch.setattr(mpv_backend, "configure_dll_search_path", configure)
    assert mpv_backend._load_mpv() is load.return_value
    discover.assert_called_once_with("mpv")
    load.assert_called_once_with(library or "libmpv.so.2")
    extract.assert_not_called()
    configure.assert_not_called()


def test_windows_mpv_keeps_bundled_dll_loading(tmp_path, monkeypatch):
    dll = tmp_path / "libmpv-2.dll"
    dll.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mpv_backend, "_mpv_lib", None)
    monkeypatch.setattr(mpv_backend, "_mpv_candidates", lambda: [dll])
    configure = MagicMock()
    load = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(mpv_backend.ctypes, "CDLL", load)
    monkeypatch.setattr(mpv_backend, "configure_dll_search_path", configure)
    mpv_backend._load_mpv()
    configure.assert_called_once_with([dll.parent])
    load.assert_called_once_with(str(dll))


def test_runtime_roots_include_frozen_locations(tmp_path, monkeypatch):
    exe_dir = tmp_path / "HexPlayer"
    internal_dir = exe_dir / "_internal"
    src_dir = tmp_path / "src"
    internal_dir.mkdir(parents=True)
    src_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "HexPlayer.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(internal_dir), raising=False)
    monkeypatch.setattr(runtime_dlls, "__file__", str(src_dir / "runtime_dlls.py"))

    roots = runtime_dlls.runtime_roots()

    assert exe_dir.resolve() in roots
    assert internal_dir.resolve() in roots
    assert src_dir.resolve() in roots
    assert len(roots) == len(set(roots))


def test_configure_dll_search_path_keeps_directory_handles(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    handles = []

    def add_dll_directory(path):
        handle = object()
        handles.append((path, handle))
        return handle

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setattr(os, "add_dll_directory", add_dll_directory, raising=False)
    monkeypatch.setattr(runtime_dlls, "_dll_directory_handles", [])
    monkeypatch.setattr(runtime_dlls, "_registered_dll_directories", set())

    roots = runtime_dlls.configure_dll_search_path([runtime_dir])

    assert runtime_dir.resolve() in roots
    assert os.environ["PATH"].split(os.pathsep)[0] == str(runtime_dir.resolve())
    assert handles[-1][1] in runtime_dlls._dll_directory_handles


def test_wayland_session_prefers_xwayland_backend(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("GDK_BACKEND", raising=False)

    runtime_dlls.configure_linux_display_backend()

    # mpv can only embed video via "wid" on X11, so we force XWayland (with a
    # native Wayland fallback so the app still launches if XWayland is missing).
    assert os.environ["GDK_BACKEND"] == "x11,wayland"


def test_explicit_gdk_backend_is_respected(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("GDK_BACKEND", "wayland")

    runtime_dlls.configure_linux_display_backend()

    assert os.environ["GDK_BACKEND"] == "wayland"


def test_x11_session_is_left_untouched(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("GDK_BACKEND", raising=False)

    runtime_dlls.configure_linux_display_backend()

    assert "GDK_BACKEND" not in os.environ


def test_non_linux_platform_is_left_untouched(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("GDK_BACKEND", raising=False)

    runtime_dlls.configure_linux_display_backend()

    assert "GDK_BACKEND" not in os.environ
