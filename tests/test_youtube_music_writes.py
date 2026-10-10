"""Tests for YouTube Music write operations: confirm dialog, run_write, panel."""

from unittest.mock import MagicMock, patch

import pytest

from youtube_music import actions
from youtube_music.errors import AuthRequiredError


class _SyncThread:
    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _sync_env():
    """Patch Thread + wx.CallAfter so run_write executes synchronously."""
    return (
        patch("youtube_music.actions.Thread", _SyncThread),
        patch("youtube_music.actions.wx.CallAfter", lambda f, *a: f(*a)),
    )


# -- confirm_destructive -----------------------------------------------------


def test_confirm_destructive_yes():
    from youtube_music.dialogs import confirm_destructive

    dlg = MagicMock()
    with (
        patch("youtube_music.dialogs.wx.MessageDialog", return_value=dlg),
        patch("youtube_music.dialogs.wx.ID_YES", 5),
        patch("youtube_music.dialogs.speak") as speak,
    ):
        dlg.ShowModal.return_value = 5
        assert confirm_destructive(None, "delete?") is True
    speak.assert_called_once_with("delete?")
    dlg.Destroy.assert_called_once()


def test_confirm_destructive_no():
    from youtube_music.dialogs import confirm_destructive

    dlg = MagicMock()
    with (
        patch("youtube_music.dialogs.wx.MessageDialog", return_value=dlg),
        patch("youtube_music.dialogs.wx.ID_YES", 5),
        patch("youtube_music.dialogs.speak"),
    ):
        dlg.ShowModal.return_value = 99
        assert confirm_destructive(None, "delete?") is False


# -- run_write ---------------------------------------------------------------


def test_run_write_success_refreshes():
    panel = MagicMock()
    fn = MagicMock()
    t, c = _sync_env()
    with t, c, patch("youtube_music.actions.speak") as speak:
        actions.run_write(None, panel, fn, success_msg="done", refresh=True)
    fn.assert_called_once()
    speak.assert_called_with("done")
    panel.reload_current.assert_called_once()


def test_run_write_no_refresh():
    panel = MagicMock()
    t, c = _sync_env()
    with t, c, patch("youtube_music.actions.speak"):
        actions.run_write(None, panel, MagicMock(), success_msg="ok", refresh=False)
    panel.reload_current.assert_not_called()


def test_run_write_destructive_cancelled():
    panel = MagicMock()
    fn = MagicMock()
    with (
        patch("youtube_music.actions.confirm_destructive", return_value=False),
        patch("youtube_music.actions.speak"),
    ):
        actions.run_write(
            None, panel, fn, success_msg="x", destructive=True, confirm_text="sure?"
        )
    fn.assert_not_called()


def test_run_write_destructive_confirmed():
    panel = MagicMock()
    fn = MagicMock()
    t, c = _sync_env()
    with (
        t,
        c,
        patch("youtube_music.actions.confirm_destructive", return_value=True),
        patch("youtube_music.actions.speak"),
    ):
        actions.run_write(
            None, panel, fn, success_msg="x", destructive=True, confirm_text="sure?"
        )
    fn.assert_called_once()


def test_run_write_auth_error_prompts_sign_in():
    panel = MagicMock()

    def boom():
        raise AuthRequiredError("nope")

    t, c = _sync_env()
    with t, c, patch("youtube_music.actions.speak"):
        actions.run_write(None, panel, boom, success_msg="x")
    panel.prompt_sign_in.assert_called_once()


def test_run_write_generic_error_speaks_failure():
    panel = MagicMock()

    def boom():
        raise ValueError("bad")

    t, c = _sync_env()
    with t, c, patch("youtube_music.actions.speak") as speak:
        actions.run_write(None, panel, boom, success_msg="x")
    panel.reload_current.assert_not_called()
    assert speak.called


# -- panel write methods -----------------------------------------------------


@pytest.fixture
def panel():
    with (
        patch("youtube_music.music_panel.apply_theme"),
        patch("youtube_browser.scraper.Scraper", MagicMock()),
    ):
        from youtube_music.music_panel import YouTubeMusicPanel

        return YouTubeMusicPanel(MagicMock(), MagicMock())


def _capture_write(panel):
    """Patch run_write to run fn against a mock service and capture kwargs."""
    service = MagicMock()
    captured = {}

    def fake_run_write(frame, p, fn, **kwargs):
        captured["kwargs"] = kwargs
        captured["result"] = fn()

    return service, captured, fake_run_write


def test_like_row(panel):
    service, captured, frw = _capture_write(panel)
    with (
        patch("youtube_music.music_panel.actions.run_write", frw),
        patch("youtube_music.music_panel.get_service", return_value=service),
    ):
        panel.like_row({"videoId": "v1", "title": "Song"})
    service.rate_song.assert_called_once_with("v1", "LIKE")
    assert captured["kwargs"]["refresh"] is False


def test_unsubscribe_is_destructive(panel):
    service, captured, frw = _capture_write(panel)
    with (
        patch("youtube_music.music_panel.actions.run_write", frw),
        patch("youtube_music.music_panel.get_service", return_value=service),
    ):
        panel.unsubscribe({"type": "artist", "browseId": "UCx", "title": "Artist"})
    service.unsubscribe_artists.assert_called_once_with(["UCx"])
    assert captured["kwargs"]["destructive"] is True


def test_delete_playlist_is_destructive(panel):
    service, captured, frw = _capture_write(panel)
    with (
        patch("youtube_music.music_panel.actions.run_write", frw),
        patch("youtube_music.music_panel.get_service", return_value=service),
    ):
        panel.delete_playlist({"type": "playlist", "playlistId": "PL1", "title": "P"})
    service.delete_playlist.assert_called_once_with("PL1")
    assert captured["kwargs"]["destructive"] is True


def test_remove_from_playlist_passes_set_video_id(panel):
    service, _captured, frw = _capture_write(panel)
    with (
        patch("youtube_music.music_panel.actions.run_write", frw),
        patch("youtube_music.music_panel.get_service", return_value=service),
    ):
        panel.remove_from_playlist(
            "PL1", {"videoId": "v1", "setVideoId": "s1", "title": "T"}
        )
    service.remove_playlist_items.assert_called_once_with(
        "PL1", [{"videoId": "v1", "setVideoId": "s1"}]
    )


def test_remove_from_history_requires_token(panel):
    with (
        patch("youtube_music.music_panel.actions.run_write") as frw,
        patch("youtube_music.music_panel.speak"),
    ):
        panel.remove_from_history({"videoId": "v1", "title": "T"})  # no feedbackToken
    frw.assert_not_called()


def test_add_to_library_requires_token(panel):
    with (
        patch("youtube_music.music_panel.actions.run_write") as frw,
        patch("youtube_music.music_panel.speak"),
    ):
        panel.add_to_library({"videoId": "v1", "title": "T", "feedbackTokens": None})
    frw.assert_not_called()
