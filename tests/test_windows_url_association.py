import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import windows_url_association as association


@pytest.fixture
def linux_integration(monkeypatch, tmp_path):
    monkeypatch.setattr(association.sys, "platform", "linux")
    monkeypatch.setattr(association.sys, "frozen", False, raising=False)
    monkeypatch.setattr(association.paths, "settings_path", str(tmp_path / "settings"))
    monkeypatch.setattr(
        association.paths,
        "get_config_root",
        lambda: str(tmp_path / "config"),
        raising=False,
    )
    monkeypatch.setattr(
        association.paths,
        "get_data_root",
        lambda: str(tmp_path / "data"),
        raising=False,
    )
    monkeypatch.setattr(
        association.paths, "get_app_path", lambda: str(tmp_path / "app space")
    )
    monkeypatch.setattr(association, "_get_winreg", Mock(side_effect=AssertionError))
    monkeypatch.setattr(
        association.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(stdout="hexplayer.desktop\n")),
    )
    return tmp_path


def test_linux_native_manifests_and_launcher(linux_integration, monkeypatch):
    chmod = Mock()
    monkeypatch.setattr(association.os, "chmod", chmod)
    monkeypatch.setattr(association.os, "access", lambda *_: True)
    assert association.register_native_messaging_host()
    launcher = Path(association.get_native_host_executable_path())
    assert launcher.read_bytes().startswith(b"#!/bin/sh\nexec ")
    assert b'"$@"\n' in launcher.read_bytes()
    assert b"\r" not in launcher.read_bytes()
    chmod.assert_called_once_with(str(launcher), 0o700)
    manifests = association.get_linux_native_host_manifest_paths()
    assert len(manifests) == 4
    for path in manifests:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        assert Path(path).name == "com.hexplayer.link_helper.json"
        assert manifest["path"] == str(launcher)
        assert manifest["allowed_origins"] == [
            f"chrome-extension://{association.EXTENSION_ID}/"
        ]
        assert str(linux_integration / "config") in path
    assert association.is_native_messaging_host_registered()
    Path(manifests[0]).write_text("{}", encoding="utf-8")
    assert not association.is_native_messaging_host_registered()
    assert association.unregister_native_messaging_host()
    assert not launcher.exists()
    assert all(not Path(path).exists() for path in manifests)
    assert association.unregister_native_messaging_host()


def test_linux_protocol_registration_and_cleanup(linux_integration):
    assert association.register_hexplayer_protocol()
    desktop = linux_integration / "data" / "applications" / "hexplayer.desktop"
    content = desktop.read_text(encoding="utf-8")
    assert "MimeType=x-scheme-handler/hexplayer;" in content
    assert "accessible_youtube_downloader_pro.py" in content
    assert " %u\n" in content
    assert "%1" not in content
    association.subprocess.run.assert_called_once_with(
        ["xdg-mime", "default", "hexplayer.desktop", "x-scheme-handler/hexplayer"],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert association.is_hexplayer_protocol_registered()
    config = linux_integration / "config"
    config.mkdir()
    mimeapps = config / "mimeapps.list"
    mimeapps.write_text(
        "[Default Applications]\nx-scheme-handler/hexplayer=hexplayer.desktop;other.desktop;\ntext/plain=editor.desktop;\n",
        encoding="utf-8",
    )
    assert association.unregister_hexplayer_protocol()
    assert not desktop.exists()
    assert "hexplayer.desktop" not in mimeapps.read_text(encoding="utf-8")
    assert "other.desktop;" in mimeapps.read_text(encoding="utf-8")
    assert "editor.desktop;" in mimeapps.read_text(encoding="utf-8")
    assert association.unregister_hexplayer_protocol()


def test_linux_missing_xdg_mime_returns_failure(linux_integration):
    association.subprocess.run.side_effect = FileNotFoundError
    assert not association.register_hexplayer_protocol()
    assert not association.is_hexplayer_protocol_registered()


def test_linux_frozen_names(linux_integration, monkeypatch):
    monkeypatch.setattr(association.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        association.sys, "executable", str(linux_integration / "HexPlayer")
    )
    assert association.get_native_host_executable_path() == str(
        linux_integration / "HexPlayerNativeHost"
    )
    assert "accessible_youtube_downloader_pro.py" not in association.get_open_command()
    assert association.get_open_command().endswith(" %u")


def test_desktop_command_escapes_reserved_characters():
    assert association._desktop_quote('/a b/100%/$`"\\') == '"/a b/100%%/\\$\\`\\"\\\\"'
    with pytest.raises(ValueError):
        association._desktop_quote("/bad\npath")


@pytest.mark.skipif(os.name == "nt", reason="Requires a POSIX shell")
def test_linux_source_launcher_executes_with_arguments(linux_integration, monkeypatch):
    import subprocess

    app = linux_integration / "app space"
    app.mkdir()
    (app / "native_messaging_host.py").write_text(
        "import sys\nprint(sys.argv[1])\n", encoding="utf-8"
    )
    association._write_linux_launcher()
    result = subprocess.check_output(
        [association._linux_launcher_path(), "browser argument"], text=True
    )
    assert result.strip() == "browser argument"


class FakeKey:
    def __init__(self, root, path):
        self.root = root
        self.path = path


class FakeWinReg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    KEY_READ = 2
    KEY_WRITE = 4
    REG_SZ = 1

    def __init__(self):
        self.keys = set()
        self.values = {}

    def add_key(self, root, path):
        parts = path.split("\\")
        for index in range(1, len(parts) + 1):
            self.keys.add((root, "\\".join(parts[:index])))

    def set_value(self, root, path, name, value):
        self.add_key(root, path)
        self.values[(root, path, name)] = value

    def CreateKeyEx(self, root, path, *_args):
        self.add_key(root, path)
        return FakeKey(root, path)

    def SetValueEx(self, key, name, _reserved, _type, value):
        self.values[(key.root, key.path, name)] = value

    def OpenKey(self, root, path, *_args):
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        return FakeKey(root, path)

    def QueryValueEx(self, key, name):
        try:
            return self.values[(key.root, key.path, name)], self.REG_SZ
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def DeleteValue(self, key, name):
        try:
            del self.values[(key.root, key.path, name)]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def EnumKey(self, key, index):
        prefix = f"{key.path}\\"
        children = sorted(
            {
                path[len(prefix) :].split("\\", 1)[0]
                for root, path in self.keys
                if root == key.root and path.startswith(prefix)
            }
        )
        if index >= len(children):
            raise OSError
        return children[index]

    def DeleteKey(self, root, path):
        prefix = f"{path}\\"
        if any(
            existing_root == root and existing_path.startswith(prefix)
            for existing_root, existing_path in self.keys
        ):
            raise OSError("key has subkeys")
        self.keys.discard((root, path))
        for key in list(self.values):
            if key[0] == root and key[1] == path:
                del self.values[key]

    def CloseKey(self, _key):
        pass


@pytest.fixture
def fake_registry(monkeypatch):
    fake = FakeWinReg()
    monkeypatch.setattr(association, "_get_winreg", lambda: fake)
    monkeypatch.setattr(association.sys, "platform", "win32")
    monkeypatch.setattr(association, "_notify_assoc_changed", lambda: None)
    return fake


def seed_legacy_registration(fake_registry):
    root = fake_registry.HKEY_CURRENT_USER
    fake_registry.set_value(
        root,
        association.REGISTERED_APPLICATIONS_PATH,
        association.APP_REG_NAME,
        association.CAPABILITIES_PATH,
    )
    fake_registry.set_value(
        root,
        rf"{association.CAPABILITIES_PATH}\URLAssociations",
        "http",
        association.PROG_ID,
    )
    fake_registry.set_value(
        root,
        rf"{association.CAPABILITIES_PATH}\URLAssociations",
        "https",
        association.PROG_ID,
    )
    fake_registry.set_value(
        root,
        rf"{association.PROG_ID_PATH}\shell\open\command",
        "",
        '"C:\\HexPlayer.exe" "%1"',
    )
    fake_registry.set_value(
        root,
        rf"{association.APPLICATION_PATH}\shell\open\command",
        "",
        '"C:\\HexPlayer.exe" "%1"',
    )


def test_cleanup_legacy_http_url_handler_removes_registered_keys(fake_registry):
    seed_legacy_registration(fake_registry)

    assert association.cleanup_legacy_http_url_handler() is True

    root = fake_registry.HKEY_CURRENT_USER
    assert (
        root,
        association.REGISTERED_APPLICATIONS_PATH,
        association.APP_REG_NAME,
    ) not in fake_registry.values
    assert all(
        path != association.CAPABILITIES_PATH for _root, path in fake_registry.keys
    )
    assert all(path != association.PROG_ID_PATH for _root, path in fake_registry.keys)
    assert all(
        path != association.APPLICATION_PATH for _root, path in fake_registry.keys
    )


def test_cleanup_legacy_http_url_handler_is_idempotent(fake_registry):
    assert association.cleanup_legacy_http_url_handler() is True


def test_is_legacy_http_url_handler_registered_reads_registered_app(fake_registry):
    assert association.is_legacy_http_url_handler_registered() is False
    seed_legacy_registration(fake_registry)
    assert association.is_legacy_http_url_handler_registered() is True


def test_register_hexplayer_protocol_writes_custom_scheme(fake_registry, monkeypatch):
    monkeypatch.setattr(
        association, "get_open_command", lambda: '"C:\\HexPlayer.exe" "%1"'
    )
    monkeypatch.setattr(
        association, "get_application_icon", lambda: "C:\\HexPlayer.exe,0"
    )

    assert association.register_hexplayer_protocol() is True

    root = fake_registry.HKEY_CURRENT_USER
    assert (
        fake_registry.values[(root, association.HEXPLAYER_PROTOCOL_PATH, "")]
        == "URL:HexPlayer Browser Integration"
    )
    assert (
        fake_registry.values[
            (root, association.HEXPLAYER_PROTOCOL_PATH, "URL Protocol")
        ]
        == ""
    )
    assert (
        fake_registry.values[
            (root, rf"{association.HEXPLAYER_PROTOCOL_PATH}\shell\open\command", "")
        ]
        == '"C:\\HexPlayer.exe" "%1"'
    )


def test_unregister_hexplayer_protocol_removes_custom_scheme(
    fake_registry, monkeypatch
):
    monkeypatch.setattr(
        association, "get_open_command", lambda: '"C:\\HexPlayer.exe" "%1"'
    )
    monkeypatch.setattr(
        association, "get_application_icon", lambda: "C:\\HexPlayer.exe,0"
    )
    association.register_hexplayer_protocol()

    assert association.unregister_hexplayer_protocol() is True

    assert all(
        path != association.HEXPLAYER_PROTOCOL_PATH
        for _root, path in fake_registry.keys
    )


def test_is_hexplayer_protocol_registered_checks_command(fake_registry, monkeypatch):
    monkeypatch.setattr(
        association, "get_open_command", lambda: '"C:\\HexPlayer.exe" "%1"'
    )
    monkeypatch.setattr(
        association, "get_application_icon", lambda: "C:\\HexPlayer.exe,0"
    )

    assert association.is_hexplayer_protocol_registered() is False
    association.register_hexplayer_protocol()
    assert association.is_hexplayer_protocol_registered() is True


def test_write_native_host_manifest_uses_stable_extension_id(tmp_path, monkeypatch):
    monkeypatch.setattr(association.paths, "settings_path", str(tmp_path))
    monkeypatch.setattr(
        association,
        "get_native_host_executable_path",
        lambda: "C:\\HexPlayerNativeHost.exe",
    )

    manifest_path = association.write_native_host_manifest()

    with open(manifest_path, encoding="utf-8") as file:
        manifest = json.load(file)
    assert manifest == {
        "name": association.NATIVE_HOST_NAME,
        "description": "HexPlayer browser integration",
        "path": "C:\\HexPlayerNativeHost.exe",
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{association.EXTENSION_ID}/"],
    }


def test_register_native_messaging_host_writes_all_browser_keys(
    fake_registry,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(association.paths, "settings_path", str(tmp_path))
    monkeypatch.setattr(
        association,
        "get_native_host_executable_path",
        lambda: "C:\\HexPlayerNativeHost.exe",
    )

    assert association.register_native_messaging_host() is True

    manifest_path = association.get_native_host_manifest_path()
    root = fake_registry.HKEY_CURRENT_USER
    for key_path in association.NATIVE_HOST_REGISTRY_PATHS:
        assert fake_registry.values[(root, key_path, "")] == manifest_path
    assert association.is_native_messaging_host_registered() is True


def test_unregister_native_messaging_host_removes_registry_and_manifest(
    fake_registry,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(association.paths, "settings_path", str(tmp_path))
    monkeypatch.setattr(
        association,
        "get_native_host_executable_path",
        lambda: "C:\\HexPlayerNativeHost.exe",
    )
    association.register_native_messaging_host()

    assert association.unregister_native_messaging_host() is True

    root = fake_registry.HKEY_CURRENT_USER
    assert all(
        (root, key_path, "") not in fake_registry.values
        for key_path in association.NATIVE_HOST_REGISTRY_PATHS
    )
    assert not association.is_native_messaging_host_registered()
