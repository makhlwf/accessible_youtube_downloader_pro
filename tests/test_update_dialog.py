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
        def __init__(self, parent, new_version, whats_new, **kwargs):
            self.parent = parent
            self.new_version = new_version
            self.whats_new = whats_new
            self.url = kwargs.get("url", "")

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

    assert captured["args"] == (
        top_window,
        "https://example.com/download/HexPlayer.exe",
    )
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


def test_update_check_dialog_on_open_browser(monkeypatch):
    dialog = object.__new__(update_check_dialog.UpdateCheckDialog)
    dialog.url = "https://example.com/update.exe"
    dialog.EndModal = Mock()
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))

    dialog.onOpenBrowser(None)

    assert opened == ["https://example.com/update.exe"]
    dialog.EndModal.assert_called_once_with(update_check_dialog.wx.ID_CANCEL)


def test_update_dialog_on_open_browser(monkeypatch):
    dialog = object.__new__(update_dialog.UpdateDialog)
    dialog.url = "https://example.com/update.exe"
    dialog.download = True
    dialog.cleanupDownload = Mock()
    dialog.EndModal = Mock()
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))

    dialog.onOpenBrowser(None)

    assert opened == ["https://example.com/update.exe"]
    assert dialog.download is False
    dialog.cleanupDownload.assert_called_once()
    dialog.EndModal.assert_called_once_with(update_dialog.wx.ID_CANCEL)


def test_inno_setup_run_section_launches_on_silent_install():
    from pathlib import Path

    inno_path = (
        Path(__file__).resolve().parent.parent / "packaging" / "windows" / "inno.iss"
    )
    assert inno_path.exists(), f"{inno_path} does not exist"

    content = inno_path.read_text(encoding="utf-8")
    run_section = content.split("[Run]", 1)[1].split("[", 1)[0]

    # Verify that the main app launch entry exists in [Run]
    assert 'Filename: "{app}\\{#MyAppExeName}"' in run_section
    # Verify that skipifsilent is NOT present so the app runs after silent update installation
    assert "skipifsilent" not in run_section
    # Verify that postinstall and nowait flags are present
    assert "nowait" in run_section
    assert "postinstall" in run_section
