from types import SimpleNamespace
from unittest.mock import Mock

import wx

from gui import download_complete_dialog, download_dialog, settings_dialog


def test_linux_download_actions_open_default_application(monkeypatch, tmp_path):
    monkeypatch.setattr(download_complete_dialog.sys, "platform", "linux")
    opened = Mock(return_value=True)
    monkeypatch.setattr(wx, "LaunchDefaultApplication", opened, raising=False)
    dialog = object.__new__(download_complete_dialog.DownloadCompleteDialog)
    dialog.file_path = str(tmp_path / "video.mp4")
    dialog.folder_path = str(tmp_path)
    dialog.EndModal = Mock()
    dialog.on_play(None)
    opened.assert_called_with(dialog.file_path)
    dialog.on_show_file(None)
    opened.assert_called_with(str(tmp_path))
    dialog.on_open_folder(None)
    opened.assert_called_with(str(tmp_path))
    assert dialog.EndModal.call_count == 3


def test_linux_open_failure_keeps_download_dialog_open(monkeypatch):
    monkeypatch.setattr(
        wx, "LaunchDefaultApplication", Mock(return_value=False), raising=False
    )
    error = Mock()
    monkeypatch.setattr(download_complete_dialog.utils, "show_error", error)
    dialog = object.__new__(download_complete_dialog.DownloadCompleteDialog)
    dialog.file_path = "/missing.mp4"
    dialog.EndModal = Mock()
    dialog.on_play(None)
    error.assert_called_once()
    dialog.EndModal.assert_not_called()


def test_download_selectors_use_paths_default(monkeypatch, tmp_path):
    default = str(tmp_path / "downloads")
    monkeypatch.setattr(
        download_dialog.paths, "get_default_download_dir", lambda: default
    )
    selector = Mock(return_value="")
    monkeypatch.setattr(wx, "DirSelector", selector, raising=False)
    download = object.__new__(download_dialog.DownloadDialog)
    download.onChangePath(None)
    assert selector.call_args.args[1] == default
    settings = object.__new__(settings_dialog.SettingsDialog)
    settings.onChange(None)
    assert selector.call_args.args[1] == default


def test_linux_browser_integration_checkbox_enabled(monkeypatch):
    monkeypatch.setattr(settings_dialog.sys, "platform", "linux")
    monkeypatch.setattr(settings_dialog, "config_get", lambda *_: False)
    monkeypatch.setattr(
        settings_dialog.utils,
        "get_player_client_choices",
        lambda: [("default", "Default")],
    )
    dialog = object.__new__(settings_dialog.SettingsDialog)
    dialog.getPlayerClientSelection = Mock(return_value=0)
    dialog._new_page = Mock(return_value=(wx.Panel(None), wx.BoxSizer(wx.VERTICAL)))
    dialog._build_advanced_page()
    assert dialog.browserIntegration.IsEnabled()


def test_linux_integration_failure_rolls_back_preference(monkeypatch):
    monkeypatch.setattr(settings_dialog.sys, "platform", "linux")
    values = {"browser_integration": False, "pot_provider_enabled": False}
    monkeypatch.setattr(settings_dialog, "config_get", lambda key: values.get(key, "0"))
    monkeypatch.setattr(
        settings_dialog, "config_set", lambda key, value: values.update({key: value})
    )
    monkeypatch.setattr(
        settings_dialog.windows_url_association,
        "register_browser_integration",
        lambda: False,
    )
    message = Mock()
    monkeypatch.setattr(wx, "MessageBox", message)
    dialog = object.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {"browser_integration": True}
    dialog.validate_cookies_path = lambda *_: True
    dialog.audioQuality2 = SimpleNamespace(Selection=0)
    dialog.formats = SimpleNamespace(Selection=0)
    dialog.videoQuality = SimpleNamespace(Selection=0)
    dialog.audioQuality = SimpleNamespace(Selection=0)
    dialog.audioOutputDevices = [{"id": ""}]
    dialog.audioOutputDevice = SimpleNamespace(Selection=0)
    dialog.playbackSpeedStep = Mock()
    dialog._save_sponsorblock_settings = Mock()
    dialog.theme_keys = ["System Default"]
    dialog.themeBox = SimpleNamespace(Selection=0)
    dialog.languageBox = SimpleNamespace(
        Selection=0, GetStringSelection=Mock(return_value="en")
    )
    dialog.Destroy = Mock()
    dialog.EndModal = Mock()
    dialog.onOk(None)
    assert values["browser_integration"] is False
    assert "browser integration" in message.call_args_list[0].args[0]
