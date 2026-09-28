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


def test_ensure_vulkan_dependency_copies_when_missing(tmp_path, monkeypatch):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_vulkan = source_dir / "vulkan-1.dll"
    source_vulkan.write_bytes(b"VULKAN")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mpv_backend, "runtime_roots", lambda: [source_dir])

    mpv_backend._ensure_vulkan_dependency(target_dir)

    target_vulkan = target_dir / "vulkan-1.dll"
    assert target_vulkan.is_file()
    assert target_vulkan.read_bytes() == b"VULKAN"


def test_ensure_vulkan_dependency_skips_when_already_exists(tmp_path, monkeypatch):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target_vulkan = target_dir / "vulkan-1.dll"
    target_vulkan.write_bytes(b"EXISTING")

    monkeypatch.setattr(sys, "platform", "win32")
    mpv_backend._ensure_vulkan_dependency(target_dir)

    assert target_vulkan.read_bytes() == b"EXISTING"


def test_windows_mpv_falls_back_to_winmode_zero_on_oserror(tmp_path, monkeypatch):
    dll = tmp_path / "libmpv-2.dll"
    dll.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mpv_backend, "_mpv_lib", None)
    monkeypatch.setattr(mpv_backend, "_mpv_candidates", lambda: [dll])
    configure = MagicMock()

    mock_lib = MagicMock()

    def fake_cdll(name, *args, **kwargs):
        if kwargs.get("winmode") == 0:
            return mock_lib
        raise OSError("WinError 126: Module not found")

    monkeypatch.setattr(mpv_backend.ctypes, "CDLL", fake_cdll)
    monkeypatch.setattr(mpv_backend, "configure_dll_search_path", configure)

    lib = mpv_backend._load_mpv()
    assert lib is mock_lib


def test_windows_mpv_raises_informative_error_when_vulkan_missing(
    tmp_path, monkeypatch
):
    dll = tmp_path / "libmpv-2.dll"
    dll.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(mpv_backend, "_mpv_lib", None)
    monkeypatch.setattr(mpv_backend, "_mpv_candidates", lambda: [dll])
    monkeypatch.setattr(mpv_backend, "runtime_roots", lambda *args, **kwargs: [])
    monkeypatch.setenv("WINDIR", str(tmp_path / "nonexistent_windir"))
    configure = MagicMock()

    def fail_cdll(*args, **kwargs):
        raise OSError("WinError 126: Module not found")

    monkeypatch.setattr(mpv_backend.ctypes, "CDLL", fail_cdll)
    monkeypatch.setattr(mpv_backend, "configure_dll_search_path", configure)

    with pytest.raises(mpv_backend.MPVError, match="vulkan-1.dll is missing"):
        mpv_backend._load_mpv()


def test_validate_package_layout_requires_vulkan_on_windows(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    build_script_path = Path(__file__).resolve().parents[1] / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", build_script_path)
    assert spec and spec.loader
    build_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_script)

    package_dir = tmp_path / "HexPlayer"
    internal_dir = package_dir / "_internal"
    internal_dir.mkdir(parents=True)
    monkeypatch.setattr(build_script, "PACKAGE_DIR", package_dir)
    monkeypatch.setattr(sys, "platform", "win32")

    (package_dir / "HexPlayer.exe").write_bytes(b"")
    (package_dir / "HexPlayerNativeHost.exe").write_bytes(b"")
    ext_dir = internal_dir / "browser_extension"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_bytes(b"{}")
    (internal_dir / "_cffi_backend.pyd").write_bytes(b"")
    prism_dir = internal_dir / "prism" / "_native"
    prism_dir.mkdir(parents=True)
    (prism_dir / "_prism_cffi.pyd").write_bytes(b"")
    (prism_dir / "prism.dll").write_bytes(b"")

    with pytest.raises(RuntimeError, match="vulkan-1.dll"):
        build_script.validate_package_layout()

    (internal_dir / "libmpv-2.dll").write_bytes(b"")
    (internal_dir / "vulkan-1.dll").write_bytes(b"")
    build_script.validate_package_layout()
