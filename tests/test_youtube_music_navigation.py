"""Tests for the YouTube Music navigation stack and view controllers."""

from unittest.mock import MagicMock

from youtube_music.base_view import BaseView, CollectionView
from youtube_music.navigation import ViewStack


def test_view_stack_push_pop_reset():
    stack = ViewStack()
    assert stack.current is None
    assert stack.can_go_back() is False
    a, b = object(), object()
    stack.reset(a)
    assert stack.current is a
    assert stack.can_go_back() is False
    stack.push(b)
    assert stack.current is b
    assert stack.can_go_back() is True
    assert stack.pop() is b
    assert stack.current is a
    # Cannot pop the root.
    assert stack.pop() is None
    assert stack.current is a


def _panel():
    panel = MagicMock()
    panel.scraper = None
    return panel


def test_base_view_display_lines_statuses():
    view = BaseView(_panel(), "T")
    view.status = "auth"
    assert "تسجيل" in view.display_lines()[0]
    view.status = "error"
    assert len(view.display_lines()) == 1
    view.status = "empty"
    view.rows = []
    assert len(view.display_lines()) == 1
    view.status = "ok"
    view.rows = [{"title": "Song", "subtitle": "Artist", "duration": "2:00"}]
    assert view.display_lines() == ["Song - Artist (2:00)"]


def test_base_view_activate_plays_song():
    panel = _panel()
    view = BaseView(panel, "T")
    view.status = "ok"
    view.rows = [{"videoId": "v1", "title": "Song"}]
    view.on_activate(0, audio_mode=True)
    panel.play.assert_called_once()


def test_base_view_activate_opens_collections():
    panel = _panel()
    view = BaseView(panel, "T")
    view.status = "ok"
    view.rows = [
        {"type": "album", "browseId": "MPREx", "title": "Al"},
        {"type": "artist", "browseId": "UCy", "title": "Ar"},
        {"type": "playlist", "playlistId": "PL", "title": "Pl"},
    ]
    view.on_activate(0)
    panel.open_album.assert_called_once()
    view.on_activate(1)
    panel.open_artist.assert_called_once()
    view.on_activate(2)
    panel.open_playlist.assert_called_once()


def test_base_view_activate_on_error_retries():
    panel = _panel()
    view = BaseView(panel, "T")
    view.status = "error"
    view.on_activate(0)
    panel.reload_current.assert_called_once()


def test_base_view_activate_on_auth_prompts_sign_in():
    panel = _panel()
    view = BaseView(panel, "T")
    view.status = "auth"
    view.on_activate(0)
    panel.prompt_sign_in.assert_called_once()


def test_context_actions_for_song():
    panel = _panel()
    view = BaseView(panel, "T")
    view.status = "ok"
    view.rows = [{"videoId": "v1", "title": "Song"}]
    labels = [label for label, _cb in view.context_actions(0)]
    assert any("تشغيل" in label for label in labels)
    assert any("الراديو" in label for label in labels)
    assert any("تنزيل" in label for label in labels)


def test_collection_view_uses_fetch_fn():
    panel = _panel()
    view = CollectionView(panel, "T", lambda: [{"title": "x"}])
    assert view.fetch() == [{"title": "x"}]
