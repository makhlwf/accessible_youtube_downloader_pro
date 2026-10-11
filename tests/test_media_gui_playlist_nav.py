"""Regression tests for playlist/queue navigation in :class:`MediaGui`.

Covers the YouTube Music bug where playing a track from a playlist or mix
announced "end of the list" on next/previous and never advanced, because a
``YTMusicResult`` queue (not a ``list``) fell through to the parent-listbox
navigation path and read the unrelated ``HomeScreen.home_feed_list``.

With ``playlist_mode=True`` the player must walk its own ``current_index`` over
the result queue instead, regardless of what listboxes the parent frame has.
"""

from unittest.mock import MagicMock

from media_player import media_gui
from youtube_music.adapters import YTMusicResult

ROWS = [
    {"videoId": "a1", "title": "Track 1"},
    {"videoId": "b2", "title": "Track 2"},
    {"videoId": "c3", "title": "Track 3"},
]


def _playlist_gui(monkeypatch, start_index=0):
    """A MediaGui wired for playlist-mode navigation, with changeTrack recorded."""
    spoken = []
    monkeypatch.setattr(media_gui, "speak", lambda msg: spoken.append(msg))

    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui.results = YTMusicResult(list(ROWS))
    gui.playlist_mode = True
    gui.mix_mode = False
    gui.shorts_mode = False
    gui._suggestions_mode = False
    gui.current_index = start_index
    gui.player = object()
    gui._closing = False

    # Parent deliberately exposes an (empty) home_feed_list: the pre-fix code
    # read this and announced end-of-list. playlist_mode must ignore it.
    parent = MagicMock()
    parent.home_feed_list.Selection = -1
    parent.home_feed_list.GetCount.return_value = 0
    gui.Parent = parent

    changed = []
    gui.changeTrack = lambda idx: changed.append(idx)
    return gui, changed, spoken


def test_next_advances_through_playlist(monkeypatch):
    gui, changed, spoken = _playlist_gui(monkeypatch, start_index=0)
    gui.next()
    gui.next()
    assert changed == [1, 2]
    assert gui.current_index == 2
    assert spoken == []  # no premature "end of list"


def test_next_stops_only_at_real_end(monkeypatch):
    gui, changed, spoken = _playlist_gui(monkeypatch, start_index=2)
    gui.next()
    assert changed == []
    assert gui.current_index == 2
    assert spoken == [media_gui._("نهاية القائمة")]


def test_previous_walks_back(monkeypatch):
    gui, changed, _spoken = _playlist_gui(monkeypatch, start_index=2)
    gui.previous()
    assert changed == [1]
    assert gui.current_index == 1


def test_previous_stops_at_start(monkeypatch):
    gui, changed, spoken = _playlist_gui(monkeypatch, start_index=0)
    gui.previous()
    assert changed == []
    assert gui.current_index == 0
    assert spoken == [media_gui._("بداية القائمة")]


def test_middle_track_navigates_both_ways(monkeypatch):
    """Starting at a middle index (as play_result passes start_index) is honoured."""
    gui, changed, _ = _playlist_gui(monkeypatch, start_index=1)
    gui.next()
    assert changed == [2]
    gui.previous()
    assert changed == [2, 1]


def test_play_result_forwards_playlist_mode_and_start_index(monkeypatch):
    """play_result must open the player as a self-contained playlist queue."""
    from youtube_music import playback

    captured = {}

    class FakeGui:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr("media_player.media_gui.MediaGui", FakeGui)

    rows = [
        {"videoId": "a1", "title": "T1", "audio_stream": object()},
        {"videoId": "b2", "title": "T2", "audio_stream": object()},
        {"videoId": "c3", "title": "T3", "audio_stream": object()},
    ]
    result = YTMusicResult(rows)
    frame = MagicMock()

    playback.play_result(frame, result, 1, audio_mode=True)

    assert captured["kwargs"].get("playlist_mode") is True
    assert captured["kwargs"].get("start_index") == 1
    assert captured["kwargs"].get("results") is result
    frame.Hide.assert_called_once()

