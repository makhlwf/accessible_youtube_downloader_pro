from unittest.mock import Mock

from media_player import media_gui


def test_fetch_like_count_updates_like_count_and_rating(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    gui.like_count = None
    gui.rating = None
    gui._media_token = object()
    gui._rating_revision = 0
    gui.can_update_player_ui = lambda: True
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
    gui._media_token = object()
    gui._rating_revision = 0
    gui.can_update_player_ui = lambda: True
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


def test_reaction_completion_for_previous_track_is_ignored(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._closing = False
    gui._media_token = object()
    gui._rating_revision = 0
    gui.url = "first"
    gui.rating = None
    gui.rating_request_pending = False
    gui.can_update_player_ui = lambda: True
    gui.fetch_like_count = Mock()
    workers = []
    callbacks = []
    speak = Mock()
    write = Mock(return_value={"success": True})
    monkeypatch.setattr(media_gui, "speak", speak)
    monkeypatch.setattr(media_gui, "config_get", lambda key: "test-cookie-file")
    monkeypatch.setattr(media_gui.utils, "validate_video_reaction", lambda parent: None)
    monkeypatch.setattr(media_gui.utils, "like_video", write)
    monkeypatch.setattr(
        media_gui,
        "Thread",
        lambda target, daemon: Mock(start=lambda: workers.append(target)),
    )
    monkeypatch.setattr(media_gui.wx, "CallAfter", lambda *args: callbacks.append(args))

    gui._submit_rating_change("like", "like", "Liked first")
    gui._media_token = object()
    gui.url = "second"
    workers[0]()
    callback, *args = callbacks[0]
    callback(*args)

    write.assert_called_once_with("first", "like", cookies_path="test-cookie-file")
    assert gui.rating is None
    assert gui.rating_request_pending
    speak.assert_called_once()
    gui.fetch_like_count.assert_not_called()
