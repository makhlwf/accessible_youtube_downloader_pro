import os
import sys

import runtime_dlls


def test_runtime_roots_include_frozen_locations(tmp_path, monkeypatch):
    exe_dir = tmp_path / "HexPlayer"
    internal_dir = exe_dir / "_internal"
    source_dir = tmp_path / "source"
    internal_dir.mkdir(parents=True)
    source_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "HexPlayer.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(internal_dir), raising=False)
    monkeypatch.setattr(runtime_dlls, "__file__", str(source_dir / "runtime_dlls.py"))

    roots = runtime_dlls.runtime_roots()

    assert exe_dir.resolve() in roots
    assert internal_dir.resolve() in roots
    assert source_dir.resolve() in roots
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
