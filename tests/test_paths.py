import importlib.util
import os
from pathlib import Path

import pytest

import language_handler
import paths


def load_paths():
    spec = importlib.util.spec_from_file_location("isolated_paths", paths.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", ["", "relative/config"])
def test_relative_xdg_roots_are_ignored(monkeypatch, value):
    monkeypatch.setenv("XDG_CONFIG_HOME", value)
    monkeypatch.setenv("XDG_DATA_HOME", value)
    assert paths.get_config_root() == os.path.expanduser("~/.config")
    assert paths.get_data_root() == os.path.expanduser("~/.local/share")


def test_linux_paths_and_download_defaults(monkeypatch, tmp_path):
    config = tmp_path / "config"
    data = tmp_path / "data"
    config.mkdir()
    downloads = tmp_path / "Custom Downloads"
    (config / "user-dirs.dirs").write_text(
        f'XDG_DOWNLOAD_DIR="{downloads.as_posix()}"\n', encoding="utf-8"
    )
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    module = load_paths()
    assert module.settings_path == str(data / "HexPlayer")
    assert Path(module.get_default_download_dir()) == downloads / "HexPlayer"
    assert not downloads.exists()
    assert not data.exists()
    assert Path(module.deno_install_path).name == "deno"


def test_portable_paths_stay_beside_executable(monkeypatch, tmp_path):
    (tmp_path / "portable.dat").touch()
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        paths.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False
    )
    monkeypatch.setattr(paths.sys, "executable", str(tmp_path / "HexPlayer"))
    module = load_paths()
    assert module.portable
    assert module.settings_path == str(tmp_path / "data")


def test_deno_discovery_prefers_user_update_then_system(monkeypatch, tmp_path):
    install = tmp_path / "runtime" / "deno"
    system = tmp_path / "system-deno"
    system.write_bytes(b"binary")
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths, "main_path", str(tmp_path))
    monkeypatch.setattr(paths, "get_bundled_data_path", lambda: str(tmp_path))
    monkeypatch.setattr(paths, "deno_path", str(install))
    monkeypatch.setattr(paths.shutil, "which", lambda name: str(system))
    assert paths.get_deno_path() == str(system)
    install.parent.mkdir()
    install.write_bytes(b"binary")
    assert paths.get_deno_path() == str(install)
    system.unlink()
    install.unlink()
    assert paths.get_deno_path() == str(install)


@pytest.mark.parametrize(
    ("lc_all", "lc_messages", "lang", "expected"),
    [
        ("ar_EG.UTF-8", "en_US.UTF-8", "en", "ar"),
        ("", "ar_SA.UTF-8", "en", "ar"),
        ("", "", "en_US.UTF-8", "en"),
        ("C.UTF-8", "", "ar", "en"),
        ("fr_FR.UTF-8", "", "", "en"),
    ],
)
def test_linux_locale_selection(monkeypatch, lc_all, lc_messages, lang, expected):
    monkeypatch.setattr(language_handler.sys, "platform", "linux")
    monkeypatch.setenv("LC_ALL", lc_all)
    monkeypatch.setenv("LC_MESSAGES", lc_messages)
    monkeypatch.setenv("LANG", lang)
    monkeypatch.delattr(language_handler.ctypes, "windll", raising=False)
    assert language_handler.get_default_language() == expected
