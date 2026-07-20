import json

import utils
from media_player import media_gui


def test_get_available_subtitles_prefers_manual_tracks(monkeypatch):
    info = {
        "subtitles": {
            "en": [
                {"ext": "ttml", "url": "manual-ttml", "name": "English"},
                {"ext": "vtt", "url": "manual-vtt", "name": "English"},
            ]
        },
        "automatic_captions": {
            "en": [{"ext": "json3", "url": "automatic-json", "name": "English"}],
            "ar": [{"ext": "json3", "url": "automatic-ar", "name": "Arabic"}],
        },
    }
    monkeypatch.setattr(utils, "get_media_info", lambda url: info)

    subtitles = utils.get_available_subtitles("https://youtube.com/watch?v=test")

    by_code = {subtitle["code"]: subtitle for subtitle in subtitles}
    assert by_code["en"]["url"] == "manual-vtt"
    assert by_code["en"]["source"] == "manual"
    assert by_code["ar"]["url"] == "automatic-ar"
    assert by_code["ar"]["source"] == "automatic"
    assert "تلقائي" in by_code["ar"]["label"]


def test_get_subtitle_cues_parses_json3(monkeypatch):
    info = {
        "subtitles": {
            "en": [{"ext": "json3", "url": "https://example.test/subs.json3"}]
        }
    }
    payload = {
        "events": [
            {"tStartMs": 1000, "dDurationMs": 1500, "segs": [{"utf8": "Hello"}]},
            {
                "tStartMs": 3000,
                "dDurationMs": 1200,
                "segs": [{"utf8": "<b>world</b> &amp; friends"}],
            },
        ]
    }

    class Response:
        text = json.dumps(payload)

        def raise_for_status(self):
            return None

    monkeypatch.setattr(utils, "get_media_info", lambda url: info)
    monkeypatch.setattr(utils.requests, "get", lambda url, timeout: Response())

    cues = utils.get_subtitle_cues("https://youtube.com/watch?v=test", "en")

    assert cues == [
        {"start_ms": 1000, "end_ms": 2500, "text": "Hello"},
        {"start_ms": 3000, "end_ms": 4200, "text": "world & friends"},
    ]


def test_get_subtitle_cues_parses_vtt(monkeypatch):
    info = {"subtitles": {"en": [{"ext": "vtt", "url": "https://example.test/en"}]}}
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:02.500
First line

00:00:03.000 --> 00:00:04.000 align:start
Second <i>line</i>
"""

    class Response:
        text = vtt

        def raise_for_status(self):
            return None

    monkeypatch.setattr(utils, "get_media_info", lambda url: info)
    monkeypatch.setattr(utils.requests, "get", lambda url, timeout: Response())

    cues = utils.get_subtitle_cues("https://youtube.com/watch?v=test", "en")

    assert cues == [
        {"start_ms": 1000, "end_ms": 2500, "text": "First line"},
        {"start_ms": 3000, "end_ms": 4000, "text": "Second line"},
    ]


def test_media_gui_speaks_subtitle_once_and_resets_after_seek(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.subtitle_cues = [
        {"start_ms": 1000, "end_ms": 2000, "text": "First"},
        {"start_ms": 3000, "end_ms": 4000, "text": "Second"},
    ]
    gui.last_spoken_subtitle_index = -1
    calls = []
    monkeypatch.setattr(media_gui, "speak", lambda message: calls.append(message))

    gui._speak_due_subtitle(1200)
    gui._speak_due_subtitle(1300)
    gui._speak_due_subtitle(3200)
    gui._speak_due_subtitle(900)
    gui._speak_due_subtitle(1200)

    assert calls == ["First", "Second", "First"]


def test_select_subtitle_language_loads_cues_and_starts_timer(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://youtube.com/watch?v=test"
    gui._closing = False
    gui.available_subtitles = [{"code": "en", "label": "English (en)"}]
    gui.current_subtitle_language = None
    gui.current_subtitle_label = ""
    gui.subtitle_cues = []
    gui.subtitle_cues_language = None
    gui.subtitles_enabled = False
    gui.subtitle_loading = False
    gui.subtitle_loading_key = None
    gui.last_spoken_subtitle_index = -1

    class FakeItem:
        def __init__(self):
            self.checked = False

        def Check(self, checked):
            self.checked = checked

    class FakeTimer:
        def __init__(self):
            self.started = False
            self.interval = None

        def Start(self, interval):
            self.started = True
            self.interval = interval

        def Stop(self):
            self.started = False

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    enable_item = FakeItem()
    language_item = FakeItem()
    timer = FakeTimer()
    gui.subtitlesEnableItem = enable_item
    gui.subtitle_language_items = {"en": language_item}
    gui.subtitle_timer = timer
    calls = []
    cues = [{"start_ms": 0, "end_ms": 1000, "text": "Caption"}]

    monkeypatch.setattr(media_gui, "Thread", ImmediateThread)
    monkeypatch.setattr(media_gui.wx, "CallAfter", lambda func, *args: func(*args))
    monkeypatch.setattr(media_gui, "speak", lambda message: calls.append(message))
    monkeypatch.setattr(
        media_gui.utils,
        "get_subtitle_cues",
        lambda url, language: cues,
    )

    gui.onSelectSubtitleLanguage("en")

    assert gui.subtitles_enabled is True
    assert enable_item.checked is True
    assert language_item.checked is True
    assert gui.subtitle_cues == cues
    assert gui.subtitle_cues_language == "en"
    assert timer.started is True
    assert timer.interval == 250
    assert calls == [
        "جاري تحميل الترجمة: English (en)",
        "تم تفعيل الترجمة: English (en)",
    ]
