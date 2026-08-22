import gettext
import os

import pytest
import wx

import settings_handler
import utils
from download_handler.downloader import Downloader
from gui import settings_dialog


@pytest.fixture(autouse=True)
def ensure_wx_app():
    app = wx.GetApp()
    if not app:
        app = wx.App()
    return app


def test_player_client_default_in_settings_handler():
    assert "player_client" in settings_handler.defaults
    assert settings_handler.defaults["player_client"] == "default"
    assert settings_handler.config_get("player_client") == "default"


def test_get_player_client_choices_structure():
    choices = utils.get_player_client_choices()
    assert len(choices) >= 8
    # First option must be default (yt-dlp default preferred)
    assert choices[0][0] == "default"
    client_ids = [c[0] for c in choices]
    assert "android" in client_ids
    assert "web" in client_ids
    assert "mweb" in client_ids
    assert "ios" in client_ids
    assert "tv" in client_ids
    assert "tv_embedded" in client_ids
    assert "android_vr" in client_ids
    assert "web_creator" in client_ids
    assert "web_safari" in client_ids


def test_get_configured_player_clients_default(monkeypatch):
    monkeypatch.setattr(
        utils, "config_get", lambda k: "default" if k == "player_client" else None
    )
    clients = utils.get_configured_player_clients()
    assert clients == ["android", "web"]

    monkeypatch.setattr(
        utils, "config_get", lambda k: "" if k == "player_client" else None
    )
    clients = utils.get_configured_player_clients()
    assert clients == ["android", "web"]


def test_get_configured_player_clients_specific_settings(monkeypatch):
    for client in [
        "android",
        "web",
        "mweb",
        "ios",
        "tv",
        "tv_embedded",
        "android_vr",
        "web_creator",
        "web_safari",
    ]:
        monkeypatch.setattr(
            utils, "config_get", lambda k, c=client: c if k == "player_client" else None
        )
        clients = utils.get_configured_player_clients()
        assert clients == [client]


def test_get_configured_player_clients_override(monkeypatch):
    monkeypatch.setattr(utils, "config_get", lambda k: "default")
    assert utils.get_configured_player_clients("android") == ["android"]
    assert utils.get_configured_player_clients(["ios", "web"]) == ["ios", "web"]
    assert utils.get_configured_player_clients("default") == ["android", "web"]


def test_get_ydl_instance_uses_configured_client(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(utils, "YoutubeDL", FakeYDL)

    # With default setting
    monkeypatch.setattr(
        utils, "config_get", lambda k: "default" if k == "player_client" else None
    )
    ydl = utils.get_ydl_instance()
    assert ydl.opts["extractor_args"]["youtube"]["player_client"] == ["android", "web"]

    # With specific setting
    monkeypatch.setattr(
        utils, "config_get", lambda k: "ios" if k == "player_client" else None
    )
    ydl = utils.get_ydl_instance()
    assert ydl.opts["extractor_args"]["youtube"]["player_client"] == ["ios"]

    # With direct client argument
    ydl = utils.get_ydl_instance(client=["tv"])
    assert ydl.opts["extractor_args"]["youtube"]["player_client"] == ["tv"]


def test_downloader_base_options_uses_configured_client(monkeypatch):
    monkeypatch.setattr(
        utils, "config_get", lambda k: "web" if k == "player_client" else None
    )
    downloader = Downloader(
        "https://www.youtube.com/watch?v=test", "output", "best", None, None
    )
    opts = downloader._base_options()
    assert opts["extractor_args"]["youtube"]["player_client"] == ["web"]

    monkeypatch.setattr(
        utils, "config_get", lambda k: "default" if k == "player_client" else None
    )
    opts = downloader._base_options()
    assert opts["extractor_args"]["youtube"]["player_client"] == ["android", "web"]


def test_settings_dialog_player_client_selection_helper():
    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.player_client_choices = utils.get_player_client_choices()

    assert dialog.getPlayerClientSelection("default") == 0
    android_idx = next(
        i for i, c in enumerate(dialog.player_client_choices) if c[0] == "android"
    )
    assert dialog.getPlayerClientSelection("android") == android_idx
    ios_idx = next(
        i for i, c in enumerate(dialog.player_client_choices) if c[0] == "ios"
    )
    assert dialog.getPlayerClientSelection("ios") == ios_idx
    assert dialog.getPlayerClientSelection("nonexistent") == 0


def test_settings_dialog_player_client_on_ok_saving(monkeypatch):
    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    dialog.installed_browsers = []
    frame = wx.Frame(None)
    dialog.player_client_choices = utils.get_player_client_choices()
    dialog.playerClientBox = wx.Choice(
        frame, -1, choices=[c[1] for c in dialog.player_client_choices]
    )
    dialog.videoQuality = wx.Choice(frame, -1, choices=["144p", "720p"])
    dialog.videoQuality.Selection = 1
    dialog.audioQuality = wx.Choice(frame, -1, choices=["low", "high"])
    dialog.audioQuality.Selection = 0
    dialog.audioQuality2 = wx.Choice(frame, -1, choices=["128k", "192k"])
    dialog.audioQuality2.Selection = 0
    dialog.formats = wx.Choice(frame, -1, choices=["mp4", "mp3"])
    dialog.formats.Selection = 0
    dialog.audioOutputDevices = [{"id": "", "description": "Default"}]
    dialog.audioOutputDevice = wx.Choice(frame, -1, choices=["Default"])
    dialog.audioOutputDevice.Selection = 0
    dialog.playbackSpeedStep = wx.SpinCtrlDouble(frame, -1, value="0.05")
    dialog.theme_keys = ["System Default"]
    dialog.themeBox = wx.Choice(frame, -1, choices=["System Default"])
    dialog.themeBox.Selection = 0
    dialog.languageBox = wx.Choice(frame, -1, choices=["ar", "en"])
    dialog.languageBox.Selection = 0
    dialog.cookiesPathField = wx.TextCtrl(frame, -1, value="")
    dialog.Destroy = lambda: None

    saved_config = {}
    monkeypatch.setattr(
        settings_dialog, "config_set", lambda k, v: saved_config.update({k: v})
    )
    monkeypatch.setattr(
        settings_dialog,
        "config_get",
        lambda k: saved_config.get(k, "default" if k == "lang" else 0),
    )

    # Select ios in combo
    ios_idx = next(
        i for i, c in enumerate(dialog.player_client_choices) if c[0] == "ios"
    )
    dialog.playerClientBox.Selection = ios_idx

    dialog.onOk(None)
    assert saved_config.get("player_client") == "ios"


def test_player_client_translations_in_po_mo_files():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "src", "languages")

    ar_trans = gettext.translation(
        "HexPlayer", localedir=locales_dir, languages=["ar"], fallback=True
    )
    en_trans = gettext.translation(
        "HexPlayer", localedir=locales_dir, languages=["en"], fallback=True
    )

    choices = utils.get_player_client_choices()
    for client_id, label in choices:
        en_label = en_trans.gettext(label)
        assert en_label is not None and len(en_label) > 0
        ar_label = ar_trans.gettext(label)
        assert ar_label == label

    assert en_trans.gettext(choices[0][1]) == "yt-dlp default (preferred)"
    assert (
        en_trans.gettext(utils.get_player_client_choices()[0][1])
        == "yt-dlp default (preferred)"
    )
    assert en_trans.gettext("عميل مشغل يوتيوب: ") == "YouTube player client: "
