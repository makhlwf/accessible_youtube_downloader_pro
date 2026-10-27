from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from media_player import media_gui


@pytest.fixture
def player(monkeypatch):
    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._closing = False
    gui._track_request_id = 0
    gui.player = SimpleNamespace(media=Mock())
    gui.results = [
        {"url": "first", "title": "First"},
        {"url": "second", "title": "Second"},
        {"url": "third", "title": "Third"},
    ]
    gui.audio_mode = True
    gui.shorts_mode = False
    gui.current_index = 0
    gui._perform_track_change = Mock()
    workers = []
    callbacks = []

    def thread(*, target, daemon):
        workers.append(target)
        return Mock()

    monkeypatch.setattr(media_gui, "Thread", thread)
    monkeypatch.setattr(media_gui, "speak", Mock())
    monkeypatch.setattr(media_gui, "get_playable_stream", Mock(return_value="stream"))
    monkeypatch.setattr(media_gui.wx, "CallAfter", lambda *args: callbacks.append(args))
    monkeypatch.setattr(media_gui.utils, "show_error", Mock())
    gui.workers = workers
    gui.callbacks = callbacks
    return gui


def deliver(player):
    for callback, *args in player.callbacks:
        callback(*args)
    player.callbacks.clear()


def test_only_latest_track_resolution_changes_playback(player):
    player.changeTrack(1)
    player.workers[0]()
    player.changeTrack(2)
    player.workers[1]()
    player._perform_track_change.assert_not_called()
    deliver(player)
    player._perform_track_change.assert_called_once_with("stream", "third", "Third", 2)


def test_superseded_worker_does_not_extract_or_stop_new_playback(player):
    player.changeTrack(1)
    player.changeTrack(2)
    player.player.media.stop.reset_mock()
    player.workers[0]()
    media_gui.get_playable_stream.assert_not_called()
    player.player.media.stop.assert_not_called()
    assert not player.callbacks
    player.workers[1]()
    media_gui.get_playable_stream.assert_called_once_with("third", audio_mode=True)
    player.player.media.stop.assert_not_called()


def test_stale_track_error_is_not_shown_over_latest_request(player):
    media_gui.get_playable_stream.side_effect = RuntimeError("old failure")
    player.changeTrack(1)
    player.workers[0]()
    player.changeTrack(2)
    deliver(player)
    media_gui.utils.show_error.assert_not_called()


def test_queued_track_result_is_ignored_after_close(player):
    player.changeTrack(1)
    player.workers[0]()
    player._closing = True
    player.player = None
    deliver(player)
    player._perform_track_change.assert_not_called()
    media_gui.utils.show_error.assert_not_called()


def test_return_to_same_index_does_not_accept_previous_request(player):
    player.changeTrack(1)
    player.workers[0]()
    player.changeTrack(2)
    player.changeTrack(1)
    deliver(player)
    player._perform_track_change.assert_not_called()
    player.workers[2]()
    deliver(player)
    player._perform_track_change.assert_called_once_with(
        "stream", "second", "Second", 1
    )
