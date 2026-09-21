import pytest
import wx

import utils
from gui import settings_dialog
from language_handler import get_default_language
from media_player import media_gui
from settings_handler import config_get, config_set, defaults


@pytest.fixture(autouse=True)
def ensure_wx_app():
    app = wx.App.GetInstance() or wx.App()
    yield app


def test_audio_track_settings_defaults():
    assert "force_original_audio" in defaults
    assert defaults["force_original_audio"] is False
    assert "preferred_audio_language" in defaults
    assert defaults["preferred_audio_language"] == get_default_language()

    config_set("force_original_audio", True)
    assert config_get("force_original_audio") is True
    config_set("force_original_audio", False)
    assert config_get("force_original_audio") is False

    config_set("preferred_audio_language", "es")
    assert config_get("preferred_audio_language") == "es"
    config_set("preferred_audio_language", get_default_language())


def test_settings_dialog_audio_controls(monkeypatch):
    config_set("force_original_audio", False)
    config_set("preferred_audio_language", "en")

    dlg = settings_dialog.SettingsDialog(None)
    try:
        assert hasattr(dlg, "forceOriginalAudio")
        assert dlg.forceOriginalAudio.GetValue() is False

        assert hasattr(dlg, "preferredAudioLanguage")
        current_selection = dlg.preferredAudioLanguage.GetSelection()
        assert dlg.preferred_audio_lang_choices[current_selection][0] == "en"

        # Change values
        dlg.forceOriginalAudio.SetValue(True)
        # Select Arabic (first item or find "ar")
        ar_index = dlg.getPreferredAudioLanguageSelection("ar")
        dlg.preferredAudioLanguage.SetSelection(ar_index)

        # Call onOk (simulate OK button)
        dlg.onOk(None)

        assert config_get("force_original_audio") is True
        assert config_get("preferred_audio_language") == "ar"
    finally:
        dlg.Destroy()
        config_set("force_original_audio", False)
        config_set("preferred_audio_language", get_default_language())


def test_get_audio_tracks_from_formats():
    fake_formats = [
        {
            "format_id": "video-1080",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 1080,
            "url": "http://example.com/v1080",
        },
        {
            "format_id": "audio-en-high",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 160,
            "language": "en",
            "language_preference": 10,
            "format_note": "English original",
            "url": "http://example.com/a-en-high",
        },
        {
            "format_id": "audio-en-low",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 64,
            "language": "en",
            "language_preference": 10,
            "format_note": "English original",
            "url": "http://example.com/a-en-low",
        },
        {
            "format_id": "audio-ar-high",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 160,
            "language": "ar",
            "language_preference": -1,
            "format_note": "Arabic dubbed",
            "url": "http://example.com/a-ar-high",
        },
        {
            "format_id": "audio-es-high",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 160,
            "language": "es",
            "language_preference": -1,
            "format_note": "Spanish dubbed",
            "url": "http://example.com/a-es-high",
        },
    ]

    tracks = utils.get_audio_tracks_from_formats(fake_formats)
    assert len(tracks) == 3

    en_track = next(t for t in tracks if t["id"] == "en")
    assert en_track["is_original"] is True
    assert len(en_track["formats"]) == 2

    ar_track = next(t for t in tracks if t["id"] == "ar")
    assert ar_track["is_original"] is False
    assert len(ar_track["formats"]) == 1

    es_track = next(t for t in tracks if t["id"] == "es")
    assert es_track["is_original"] is False


def test_select_audio_format_scenarios():
    fake_formats = [
        {
            "format_id": "audio-en",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "language": "en",
            "language_preference": 10,
            "format_note": "original",
            "url": "http://example.com/en",
        },
        {
            "format_id": "audio-ar",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "language": "ar",
            "language_preference": -1,
            "format_note": "dubbed",
            "url": "http://example.com/ar",
        },
    ]

    # Scenario 1: preferred=ar, force=False -> picks Arabic
    fmt, tr = utils.select_audio_format(
        fake_formats, preferred_lang="ar", force_original=False
    )
    assert fmt["format_id"] == "audio-ar"
    assert tr["id"] == "ar"

    # Scenario 2: preferred=ar, force=True -> picks English (original)
    fmt, tr = utils.select_audio_format(
        fake_formats, preferred_lang="ar", force_original=True
    )
    assert fmt["format_id"] == "audio-en"
    assert tr["id"] == "en"

    # Scenario 3: preferred=fr (not available), force=False -> fallback to English (original)
    fmt, tr = utils.select_audio_format(
        fake_formats, preferred_lang="fr", force_original=False
    )
    assert fmt["format_id"] == "audio-en"
    assert tr["id"] == "en"

    # Scenario 4: explicit audio_track_id="ar" -> picks Arabic
    fmt, tr = utils.select_audio_format(fake_formats, audio_track_id="ar")
    assert fmt["format_id"] == "audio-ar"
    assert tr["id"] == "ar"


def test_pick_best_format_integration():
    fake_formats = [
        {
            "format_id": "v720",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 720,
            "url": "http://example.com/v720",
        },
        {
            "format_id": "a-en",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "language": "en",
            "language_preference": 10,
            "format_note": "original",
            "url": "http://example.com/a-en",
        },
        {
            "format_id": "a-ar",
            "vcodec": "none",
            "acodec": "mp4a",
            "abr": 128,
            "language": "ar",
            "language_preference": -1,
            "format_note": "dubbed",
            "url": "http://example.com/a-ar",
        },
    ]

    # In video mode with preferred_audio_lang="ar"
    v_fmt, a_fmt, _height = utils.pick_best_format(
        fake_formats,
        4,
        is_video=True,
        target_height=720,
        preferred_audio_lang="ar",
        force_original=False,
    )
    assert v_fmt["format_id"] == "v720"
    assert a_fmt["format_id"] == "a-ar"

    # In audio mode with preferred_audio_lang="ar"
    fmt, a_none, _abr = utils.pick_best_format(
        fake_formats,
        1,
        is_video=False,
        preferred_audio_lang="ar",
        force_original=False,
    )
    assert fmt["format_id"] == "a-ar"
    assert a_none is None


def test_media_gui_populate_and_switch_audio_tracks(monkeypatch):
    spoken = []
    monkeypatch.setattr(media_gui, "speak", lambda msg: spoken.append(msg))

    class DummyMPV:
        def __init__(self):
            self.tracks = [
                {
                    "id": 1,
                    "type": "audio",
                    "external-filename": "http://example.com/a-en",
                    "selected": True,
                },
                {
                    "id": 2,
                    "type": "audio",
                    "external-filename": "http://example.com/a-ar",
                    "selected": False,
                },
            ]
            self.current_aid = "1"

        def get_audio_tracks(self):
            return self.tracks

        def set_audio_track(self, track_id):
            self.current_aid = str(track_id)
            for t in self.tracks:
                t["selected"] = str(t["id"]) == self.current_aid
            return True

        def add_audio_track(self, url, select=True, title="", lang=""):
            new_id = len(self.tracks) + 1
            self.tracks.append(
                {
                    "id": new_id,
                    "type": "audio",
                    "external-filename": url,
                    "selected": select,
                }
            )
            if select:
                self.current_aid = str(new_id)
            return True

    class DummyPlayer:
        def __init__(self):
            self.media = DummyMPV()

        def get_audio_tracks(self):
            return self.media.get_audio_tracks()

        def set_audio_track(self, track_id):
            return self.media.set_audio_track(track_id)

        def add_audio_track(self, url, select=True, title="", lang=""):
            return self.media.add_audio_track(
                url, select=select, title=title, lang=lang
            )

    monkeypatch.setattr(
        media_gui.wx, "CallAfter", lambda func, *args, **kwargs: func(*args, **kwargs)
    )

    class MockMenuItem:
        def __init__(self, label):
            self.label = label
            self._checked = False

        def Check(self, checked=True):
            self._checked = bool(checked)

        def IsChecked(self):
            return self._checked

        def Enable(self, enabled=True):
            pass

    class MockAudioTracksMenu:
        def __init__(self):
            self.items = []

        def GetMenuItems(self):
            return list(self.items)

        def DestroyItem(self, item):
            if item in self.items:
                self.items.remove(item)

        def AppendCheckItem(self, id, label):
            item = MockMenuItem(label)
            self.items.append(item)
            return item

        def Append(self, id, label):
            item = MockMenuItem(label)
            self.items.append(item)
            return item

    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._closing = False
    gui.IsBeingDeleted = lambda: False
    gui.Bind = lambda *args, **kwargs: None
    gui.player = DummyPlayer()
    gui.current_audio_track_id = "en"
    gui.audioTracksMenu = MockAudioTracksMenu()
    gui.available_audio_tracks = []
    gui.audio_track_items = {}

    tracks = [
        {
            "id": "en",
            "lang": "en",
            "label": "English (Original)",
            "is_original": True,
            "url": "http://example.com/a-en",
        },
        {
            "id": "ar",
            "lang": "ar",
            "label": "Arabic",
            "is_original": False,
            "url": "http://example.com/a-ar",
        },
    ]

    gui.populate_audio_tracks_menu(tracks)
    assert len(gui.audioTracksMenu.GetMenuItems()) == 2
    assert gui.audio_track_items["en"].IsChecked()
    assert not gui.audio_track_items["ar"].IsChecked()

    # Selecting the already active track
    gui.on_change_audio_track(tracks[0])
    assert any("محدد بالفعل" in s or "already selected" in s for s in spoken)

    # Selecting the Arabic track
    spoken.clear()
    gui.on_change_audio_track(tracks[1])

    # Wait for thread to finish
    import time

    for _ in range(20):
        wx.Yield()
        if gui.current_audio_track_id == "ar":
            break
        time.sleep(0.05)

    assert gui.current_audio_track_id == "ar"
    assert gui.audio_track_items["ar"].IsChecked()
    assert not gui.audio_track_items["en"].IsChecked()
    assert any("تم التبديل" in s or "Switched" in s for s in spoken)


def test_audio_track_translations_in_po_mo_files():
    import gettext
    import os

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "src", "languages")

    ar_trans = gettext.translation(
        "HexPlayer", localedir=locales_dir, languages=["ar"], fallback=True
    )
    en_trans = gettext.translation(
        "HexPlayer", localedir=locales_dir, languages=["en"], fallback=True
    )

    assert en_trans.gettext("المسارات الصوتية") == "Audio tracks"
    assert ar_trans.gettext("المسارات الصوتية") == "المسارات الصوتية"

    assert en_trans.gettext("لا توجد مسارات صوتية متاحة") == "No audio tracks available"
    assert (
        ar_trans.gettext("لا توجد مسارات صوتية متاحة") == "لا توجد مسارات صوتية متاحة"
    )

    assert (
        en_trans.gettext("تعذر تغيير المسار الصوتي") == "Could not change audio track"
    )
    assert ar_trans.gettext("تعذر تغيير المسار الصوتي") == "تعذر تغيير المسار الصوتي"

    assert (
        en_trans.gettext("لغة المسار الصوتي المفضلة: ")
        == "Preferred audio language track: "
    )
    assert (
        en_trans.gettext("فرض لغة الصوت الأصلية افتراضيًا عند تشغيل الفيديو")
        == "Force the original audio language by default when playing a video"
    )

    # Test language names translations in English
    expected_en = {
        "العربية": "Arabic",
        "الإنجليزية": "English",
        "الإسبانية": "Spanish",
        "الفرنسية": "French",
        "الألمانية": "German",
        "الإيطالية": "Italian",
        "البرتغالية": "Portuguese",
        "الروسية": "Russian",
        "اليابانية": "Japanese",
        "الكورية": "Korean",
        "الهندية": "Hindi",
        "التركية": "Turkish",
        "الإندونيسية": "Indonesian",
        "الصينية": "Chinese",
        "الفيتنامية": "Vietnamese",
        "البنغالية": "Bengali",
        "البولندية": "Polish",
        "التايلاندية": "Thai",
        "الهولندية": "Dutch",
        "السويدية": "Swedish",
        "الفارسية": "Persian",
        "الأردية": "Urdu",
    }
    for ar_name, en_name in expected_en.items():
        assert en_trans.gettext(ar_name) == en_name
        assert ar_trans.gettext(ar_name) == ar_name
