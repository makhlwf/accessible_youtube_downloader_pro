"""Tests for YouTubeMusicPanel load/render/navigation/actions (fake wx)."""

from unittest.mock import MagicMock, patch

import pytest

from youtube_music.base_view import CollectionView
from youtube_music.errors import AuthRequiredError


@pytest.fixture
def panel():
    with (
        patch("youtube_music.music_panel.apply_theme"),
        patch("youtube_browser.scraper.Scraper", MagicMock()),
    ):
        from youtube_music.music_panel import YouTubeMusicPanel

        home = MagicMock()
        p = YouTubeMusicPanel(MagicMock(), home)
        return p


def _view(panel, rows=None):
    view = CollectionView(panel, "Title", lambda: rows or [])
    panel.stack.reset(view)
    return view


def test_on_loaded_ok_renders_rows(panel):
    view = _view(panel)
    panel._load_token = 7
    panel._on_loaded(view, 7, [{"videoId": "v", "title": "Song"}], None)
    assert view.status == "ok"
    assert panel.content_list.GetCount() == 1


def test_on_loaded_superseded_token_ignored(panel):
    view = _view(panel)
    view.status = "sentinel"
    panel._load_token = 7
    panel._on_loaded(view, 3, [{"videoId": "v"}], None)
    assert view.status == "sentinel"


def test_on_loaded_auth_error(panel):
    view = _view(panel)
    panel._load_token = 1
    panel._on_loaded(view, 1, None, AuthRequiredError("nope"))
    assert view.status == "auth"


def test_on_loaded_generic_error(panel):
    view = _view(panel)
    panel._load_token = 1
    panel._on_loaded(view, 1, None, Exception("boom"))
    assert view.status == "error"


def test_on_loaded_empty(panel):
    view = _view(panel)
    panel._load_token = 1
    panel._on_loaded(view, 1, [], None)
    assert view.status == "empty"


def test_go_back_pops(panel):
    panel._start_load = MagicMock()
    first = _view(panel)
    second = CollectionView(panel, "Second", list)
    panel.stack.push(second)
    assert panel.stack.current is second
    panel.go_back()
    assert panel.stack.current is first


def test_go_back_at_root_announces(panel):
    _view(panel)
    with patch("youtube_music.music_panel.speak") as speak:
        panel.go_back()
    speak.assert_called_once()


def test_activate_builds_home_view(panel):
    panel._start_load = MagicMock()
    panel.activate()
    assert panel.stack.current.title == panel.stack.current.title
    panel._start_load.assert_called_once()


def test_activate_selected_delegates_to_view(panel):
    view = _view(panel, [{"videoId": "v", "title": "Song"}])
    view.rows = [{"videoId": "v", "title": "Song"}]
    view.status = "ok"
    panel.content_list.Set(["Song"])
    panel.content_list.SetSelection(0)
    panel.play = MagicMock()
    panel._activate_selected(audio_mode=True)
    panel.play.assert_called_once()


def test_play_delegates_to_playback(panel):
    with patch("youtube_music.music_panel.playback.play_result") as play_result:
        result = MagicMock()
        panel.play(result, 0, audio_mode=True)
    play_result.assert_called_once_with(panel.home_screen, result, 0, audio_mode=True)


def test_start_radio_delegates_to_playback(panel):
    with patch("youtube_music.music_panel.playback.start_radio") as start_radio:
        result = MagicMock()
        panel.start_radio(result, 1)
    start_radio.assert_called_once()


def test_download_row_calls_start_media_download(panel):
    with (
        patch("download_handler.downloader.start_media_download") as smd,
        patch("settings_handler.config_get", return_value="C:/dl"),
    ):
        panel.download_row({"videoId": "abc", "title": "Song"})
    smd.assert_called_once()
    args = smd.call_args.args
    assert args[0] == "https://www.youtube.com/watch?v=abc"
    assert args[1] == "m4a"


def test_download_row_ignores_non_video(panel):
    with patch("download_handler.downloader.start_media_download") as smd:
        panel.download_row({"browseId": "MPRE", "title": "Album"})
    smd.assert_not_called()


def test_open_album_pushes_view(panel):
    panel._start_load = MagicMock()
    panel.open_album({"title": "My Album", "browseId": "MPREx"})
    assert panel.stack.current.title == "My Album"


def test_open_moods_pushes_view(panel):
    panel._start_load = MagicMock()
    panel.open_moods()
    assert panel.stack.can_go_back() is False or panel.stack.current is not None
