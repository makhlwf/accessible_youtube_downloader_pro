import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils
from gui import update_check_dialog, update_dialog
from gui.update_dialog import UpdateDialog, _download_name_from_url


@pytest.mark.parametrize(
    ("system", "machine", "info", "expected_url", "expected_download"),
    [
        (
            "linux",
            "x86_64",
            {
                "version": "9.9.9",
                "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
                "platforms": {
                    "linux": {
                        "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz"
                    }
                },
            },
            "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz",
            True,
        ),
        (
            "linux",
            "AMD64",
            {
                "version": "9.9.9",
                "platforms": {
                    "linux": {
                        "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-amd64.deb"
                    }
                },
            },
            "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-amd64.deb",
            True,
        ),
        (
            "linux",
            "aarch64",
            {
                "version": "9.9.9",
                "platforms": {
                    "linux": {
                        "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz"
                    }
                },
            },
            utils.RELEASES_PAGE_URL,
            False,
        ),
        (
            "linux",
            "x86_64",
            {
                "version": "9.9.9",
                "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
            },
            utils.RELEASES_PAGE_URL,
            False,
        ),
        (
            "win32",
            "AMD64",
            {
                "version": "9.9.9",
                "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
                "platforms": {"linux": {"url": "ignored"}},
            },
            "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
            True,
        ),
    ],
)
def test_select_app_update_platform(
    monkeypatch, system, machine, info, expected_url, expected_download
):
    monkeypatch.setattr(utils.sys, "platform", system)
    monkeypatch.setattr(utils.platform, "machine", lambda: machine)
    assert utils._select_app_update(info) == (expected_url, expected_download)


@pytest.mark.parametrize(
    ("info", "expected_url", "expected_download"),
    [
        (
            {
                "version": "9.9.9",
                "platforms": {
                    "linux": {
                        "browser_download_url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz"
                    }
                },
            },
            "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz",
            True,
        ),
        (
            {
                "version": "9.9.9",
                "platforms": {
                    "linux": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-amd64.deb"
                },
            },
            "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-amd64.deb",
            True,
        ),
        (
            {
                "version": "9.9.9",
                "platforms": {
                    "linux": {
                        "url": "https://evil.example.com/HexPlayer-9.9.9-linux-x86_64.tar.gz"
                    }
                },
            },
            utils.RELEASES_PAGE_URL,
            False,
        ),
    ],
)
def test_select_app_update_linux_entry_forms(
    monkeypatch, info, expected_url, expected_download
):
    monkeypatch.setattr(utils.sys, "platform", "linux")
    monkeypatch.setattr(utils.platform, "machine", lambda: "x86_64")
    assert utils._select_app_update(info) == (expected_url, expected_download)


@pytest.mark.parametrize("system", ["linux", "win32"])
def test_check_for_updates_platform_download_and_browser_flow(monkeypatch, system):
    monkeypatch.setattr(utils.sys, "platform", system)
    monkeypatch.setattr(utils.platform, "machine", lambda: "AMD64")

    class Response:
        status_code = 200

        def json(self):
            return {
                "version": "9.9.9",
                "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
                "platforms": {
                    "linux": {
                        "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer-9.9.9-linux-x86_64.tar.gz"
                    }
                },
            }

    top_window = object()
    app = Mock()
    app.GetTopWindow.return_value = top_window
    opened = []
    dialogs = []
    monkeypatch.setattr(utils.application, "version", "1.0.0")
    monkeypatch.setattr(utils.requests, "get", Mock(return_value=Response()))
    monkeypatch.setattr(utils.wx, "CallAfter", lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(utils.wx, "GetApp", Mock(return_value=app))
    fake_update_dialog = Mock()
    monkeypatch.setattr(update_dialog, "UpdateDialog", fake_update_dialog)
    monkeypatch.setattr("webbrowser.open", lambda target: opened.append(target) or None)
    real_dialog = update_check_dialog.UpdateCheckDialog

    class InstrumentedDialog(real_dialog):
        def __init__(self, parent, new_version, whats_new, **kwargs):
            super().__init__(parent, new_version, whats_new, **kwargs)
            self.ShowModal_result = update_dialog.wx.ID_OK
            self.show_modal_count = 0
            self.end_modal_results = []
            dialogs.append(self)

        def ShowModal(self):
            self.show_modal_count += 1
            return self.ShowModal_result

        def EndModal(self, result):
            self.end_modal_result = result

    monkeypatch.setattr(update_check_dialog, "UpdateCheckDialog", InstrumentedDialog)

    utils.check_for_updates()
    dlg = dialogs[-1]
    assert dlg.url.endswith(
        "HexPlayer.exe" if system == "win32" else "linux-x86_64.tar.gz"
    )
    assert dlg.can_download is True
    assert dlg.download_btn.IsEnabled() is True

    dlg.onOpenBrowser(None)
    assert opened == [dlg.url]
    assert dlg.end_modal_result == update_dialog.wx.ID_CANCEL
    assert fake_update_dialog.call_count == 0


def test_check_for_updates_linux_without_platforms_metadata_uses_releases_fallback(
    monkeypatch,
):
    class Response:
        status_code = 200

        def json(self):
            return {
                "version": "9.9.9",
                "url": "https://github.com/o/r/releases/download/v9.9.9/HexPlayer.exe",
            }

    top_window = object()
    app = Mock()
    app.GetTopWindow.return_value = top_window
    opened = []
    dialogs = []
    monkeypatch.setattr(utils.sys, "platform", "linux")
    monkeypatch.setattr(utils.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(utils.application, "version", "1.0.0")
    monkeypatch.setattr(utils.requests, "get", Mock(return_value=Response()))
    monkeypatch.setattr(utils.wx, "CallAfter", lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(utils.wx, "GetApp", Mock(return_value=app))
    fake_update_dialog = Mock()
    monkeypatch.setattr(update_dialog, "UpdateDialog", fake_update_dialog)
    monkeypatch.setattr("webbrowser.open", lambda target: opened.append(target) or None)
    real_dialog = update_check_dialog.UpdateCheckDialog

    class InstrumentedDialog(real_dialog):
        def __init__(self, parent, new_version, whats_new, **kwargs):
            super().__init__(parent, new_version, whats_new, **kwargs)
            dialogs.append(self)

        def EndModal(self, result):
            self.end_modal_result = result

    monkeypatch.setattr(update_check_dialog, "UpdateCheckDialog", InstrumentedDialog)

    utils.check_for_updates()
    dlg = dialogs[-1]
    assert dlg.url == utils.RELEASES_PAGE_URL
    assert dlg.can_download is False
    assert dlg.download_btn.IsEnabled() is False

    dlg.onOpenBrowser(None)
    assert opened == [utils.RELEASES_PAGE_URL]
    assert dlg.end_modal_result == update_dialog.wx.ID_CANCEL
    assert fake_update_dialog.call_count == 0


def test_check_for_updates_uses_update_dialog_title_keyword(monkeypatch):
    monkeypatch.setattr(utils.sys, "platform", "win32")

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
    monkeypatch.setattr(update_dialog.sys, "platform", "win32")
    installer = tmp_path / "Hex Player.exe"
    installer.write_text("", encoding="utf-8")
    popen = Mock()
    monkeypatch.setattr(update_dialog.subprocess, "Popen", popen)

    UpdateDialog.launchInstaller(str(installer))

    popen.assert_called_once_with([str(installer), "/SILENT"], cwd=str(tmp_path))


def test_on_finished_launches_downloaded_update_path(monkeypatch, tmp_path):
    monkeypatch.setattr(update_dialog.sys, "platform", "win32")
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


def test_linux_update_offers_folder_without_executing(monkeypatch, tmp_path):
    monkeypatch.setattr(update_dialog.sys, "platform", "linux")
    archive = tmp_path / "HexPlayer.tar.gz"
    archive.write_bytes(b"archive")
    dialog = object.__new__(UpdateDialog)
    dialog.dest = None
    dialog.download = True
    dialog.status = Mock()
    dialog.EndModal = Mock()
    launch = Mock()
    exit_process = Mock()
    opened = Mock(return_value=True)
    speech = Mock()
    monkeypatch.setattr(UpdateDialog, "launchInstaller", staticmethod(launch))
    monkeypatch.setattr(update_dialog.sys, "exit", exit_process)
    monkeypatch.setattr(
        update_dialog.wx, "MessageBox", Mock(return_value=update_dialog.wx.YES)
    )
    monkeypatch.setattr(
        update_dialog.wx, "LaunchDefaultApplication", opened, raising=False
    )
    monkeypatch.setattr(update_dialog.speech_client, "speak", speech)
    dialog.onFinished(SimpleNamespace(path=str(archive)))
    launch.assert_not_called()
    exit_process.assert_not_called()
    opened.assert_called_once_with(str(tmp_path))
    assert archive.exists()
    assert not dialog.download
    assert "manually" in dialog.status.SetValue.call_args.args[0]
    assert str(archive) in speech.call_args.args[0]
    assert speech.call_args.kwargs["interrupt"] is True
    dialog.EndModal.assert_called_once_with(update_dialog.wx.ID_OK)


def test_linux_launch_installer_is_rejected(monkeypatch, tmp_path):

    monkeypatch.setattr(update_dialog.sys, "platform", "linux")
    popen = Mock()
    monkeypatch.setattr(update_dialog.subprocess, "Popen", popen)
    with pytest.raises(OSError):
        UpdateDialog.launchInstaller(str(tmp_path / "HexPlayer.tar.gz"))
    popen.assert_not_called()


def test_update_error_is_dispatched_to_gui_thread(monkeypatch):
    dialog = object.__new__(UpdateDialog)
    dialog.cleanupDownload = Mock()
    dialog.EndModal = Mock()
    queued = Mock()
    show_error = Mock()
    monkeypatch.setattr(update_dialog.wx, "CallAfter", queued)
    monkeypatch.setattr(update_dialog.utils, "show_error", show_error)
    error = OSError("download failed")
    dialog.errorAction(error, "partial")
    show_error.assert_not_called()
    dialog.cleanupDownload.assert_called_once_with("partial")
    queued.assert_called_once_with(dialog._show_download_error, error)


def test_linux_deno_zip_extract_sets_executable_bit(monkeypatch, tmp_path):
    monkeypatch.setattr(update_dialog.sys, "platform", "linux")
    chmod = Mock()
    monkeypatch.setattr(update_dialog.os, "chmod", chmod)
    binary = tmp_path / "deno"
    binary.write_bytes(b"binary")
    archive_path = tmp_path / "deno.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(binary, "deno")
    dialog = object.__new__(UpdateDialog)
    dialog.dest = str(tmp_path / "deno.zip")
    dialog.is_zip = True
    dialog.download = True
    dialog.EndModal = Mock()
    monkeypatch.setattr(update_dialog.wx, "MessageBox", Mock())
    dialog.onFinished(SimpleNamespace(path=str(archive_path)))
    chmod.assert_called_once_with(str(binary), 0o755)
    assert not archive_path.exists()
    dialog.EndModal.assert_called_once_with(update_dialog.wx.ID_OK)


def test_windows_deno_zip_extract_skips_chmod(monkeypatch, tmp_path):
    monkeypatch.setattr(update_dialog.sys, "platform", "win32")
    chmod = Mock()
    monkeypatch.setattr(update_dialog.os, "chmod", chmod)
    binary = tmp_path / "deno.exe"
    binary.write_bytes(b"binary")
    archive_path = tmp_path / "deno.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(binary, "deno.exe")
    dialog = object.__new__(UpdateDialog)
    dialog.dest = str(tmp_path / "deno.zip")
    dialog.is_zip = True
    dialog.download = True
    dialog.EndModal = Mock()
    monkeypatch.setattr(update_dialog.wx, "MessageBox", Mock())
    dialog.onFinished(SimpleNamespace(path=str(archive_path)))
    chmod.assert_not_called()
    dialog.EndModal.assert_called_once_with(update_dialog.wx.ID_OK)


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
