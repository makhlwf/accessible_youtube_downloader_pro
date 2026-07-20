from media_player import media_gui


def test_fetch_like_count_updates_like_count_and_rating(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    gui.like_count = None
    gui.rating = None
    gui.rating_request_pending = False

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(media_gui, "Thread", ImmediateThread)
    monkeypatch.setattr(
        media_gui.utils,
        "get_video_like_info",
        lambda url: {"likes": 42, "rating": "like"},
    )

    gui.fetch_like_count()

    assert gui.like_count == 42
    assert gui.rating == "like"


def test_fetch_like_count_does_not_overwrite_pending_rating(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    gui.like_count = None
    gui.rating = "dislike"
    gui.rating_request_pending = True

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(media_gui, "Thread", ImmediateThread)
    monkeypatch.setattr(
        media_gui.utils,
        "get_video_like_info",
        lambda url: {"likes": 42, "rating": "like"},
    )

    gui.fetch_like_count()

    assert gui.like_count == 42
    assert gui.rating == "dislike"


def test_rating_change_ignores_second_request_while_pending(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    gui.rating = "like"
    gui.rating_request_pending = True

    calls = []
    monkeypatch.setattr(media_gui, "speak", lambda message: calls.append(message))
    monkeypatch.setattr(
        media_gui.utils,
        "like_video",
        lambda url, action: calls.append(("like_video", action)),
    )

    gui.onDislike()

    assert gui.rating == "like"
    assert calls == ["جاري تحديث التقييم"]


def test_seek_to_timecode_sets_player_time(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.last_spoken_subtitle_index = 3
    calls = []
    spoken = []

    class FakeMedia:
        def set_time(self, milliseconds):
            calls.append(milliseconds)

    class FakePlayer:
        media = FakeMedia()

    gui.player = FakePlayer()
    monkeypatch.setattr(media_gui, "speak", lambda message: spoken.append(message))

    assert gui.seek_to_timecode("2:47") is True

    assert calls == [167000]
    assert gui.last_spoken_subtitle_index == -1
    assert spoken == ["الانتقال إلى 2:47"]


def test_toggle_repeat_turns_off_autoplay(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    state = {"repeatTracks": False, "autonext": True}
    spoken = []

    monkeypatch.setattr(media_gui, "config_get", lambda key: state[key])
    monkeypatch.setattr(
        media_gui, "config_set", lambda key, value: state.__setitem__(key, value)
    )
    monkeypatch.setattr(media_gui, "speak", lambda message: spoken.append(message))

    gui.toggleRepeatTracks()

    assert state == {"repeatTracks": True, "autonext": False}
    assert spoken == ["التكرار مفعل"]


def test_toggle_autoplay_turns_off_repeat(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    state = {"repeatTracks": True, "autonext": False}
    spoken = []

    monkeypatch.setattr(media_gui, "config_get", lambda key: state[key])
    monkeypatch.setattr(
        media_gui, "config_set", lambda key, value: state.__setitem__(key, value)
    )
    monkeypatch.setattr(media_gui, "speak", lambda message: spoken.append(message))

    gui.toggleAutoNext()

    assert state == {"repeatTracks": False, "autonext": True}
    assert spoken == ["تشغيل المقطع التالي تلقائيًا مفعل"]
