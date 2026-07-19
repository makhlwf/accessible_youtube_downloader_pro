from types import SimpleNamespace
from unittest.mock import Mock

import utils
from gui import update_check_dialog, update_dialog
from gui.update_dialog import UpdateDialog, _download_name_from_url


def test_check_for_updates_uses_update_dialog_title_keyword(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "version": "9.9.9",
                "url": "https://example.com/download/HexPlayer.exe",
                "whats_new": "Fixes",
            }

    class FakeUpdateCheckDialog:
        def __init__(self, parent, new_version, whats_new):
            self.parent = parent
            self.new_version = new_version
            self.whats_new = whats_new

        def ShowModal(self):
            return update_dialog.wx.ID_OK

        def Destroy(self):
            pass

    top_window = object()
    app = Mock()
    app.GetTopWindow.return_value = top_window
    captured = {}

    def fake_update_dialog(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(utils.application, "version", "1.0.0")
    monkeypatch.setattr(utils.requests, "get", Mock(return_value=Response()))
    monkeypatch.setattr(utils.wx, "CallAfter", lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(utils.wx, "GetApp", Mock(return_value=app))
    monkeypatch.setattr(update_check_dialog, "UpdateCheckDialog", FakeUpdateCheckDialog)
    monkeypatch.setattr(update_dialog, "UpdateDialog", fake_update_dialog)

    utils.check_for_updates()

    assert captured["args"] == (top_window, "https://example.com/download/HexPlayer.exe")
    assert captured["kwargs"] == {"title": "جاري تنزيل التحديث"}


def test_download_name_from_url_ignores_query_string():
    assert (
        _download_name_from_url("https://example.com/releases/HexPlayer.exe?download=1")
        == "HexPlayer.exe"
    )


def test_launch_installer_uses_argument_list(monkeypatch, tmp_path):
    installer = tmp_path / "Hex Player.exe"
    installer.write_text("", encoding="utf-8")
    popen = Mock()
    monkeypatch.setattr(update_dialog.subprocess, "Popen", popen)

    UpdateDialog.launchInstaller(str(installer))

    popen.assert_called_once_with([str(installer), "/SILENT"], cwd=str(tmp_path))


def test_on_finished_launches_downloaded_update_path(monkeypatch, tmp_path):
    installer = tmp_path / "HexPlayer.exe"
    installer.write_text("", encoding="utf-8")
    dialog = object.__new__(UpdateDialog)
    dialog.dest = None
    dialog.download = True
    dialog.status = Mock()
    dialog.EndModal = Mock()
    launch = Mock()

    monkeypatch.setattr(update_dialog.wx, "MessageBox", Mock())
    monkeypatch.setattr(UpdateDialog, "launchInstaller", staticmethod(launch))
    monkeypatch.setattr(update_dialog.sys, "exit", Mock())

    dialog.onFinished(SimpleNamespace(path=str(installer)))

    dialog.status.SetValue.assert_called_once_with("جاري تثبيت التحديث")
    launch.assert_called_once_with(str(installer))
    assert dialog.download is False
