"""Tests for the in-place YouTube Music flip on the HomeScreen."""

from unittest.mock import MagicMock, patch

import pytest

from accessible_youtube_downloader_pro import HomeScreen


@pytest.fixture
def home():
    with (
        patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=True,
        ),
        patch(
            "accessible_youtube_downloader_pro.browser_extension_manager.sync_browser_extension_files"
        ),
        patch("accessible_youtube_downloader_pro.TaskBarIcon"),
    ):
        yield HomeScreen(start_hidden=True)


def test_music_button_and_menu_exist(home):
    assert home.musicBtn is not None
    assert home.musicItem is not None
    assert home.music_panel is None  # built lazily


def test_open_music_flips_in_place(home):
    fake_panel = MagicMock()
    with (
        patch("youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel),
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
    assert home.music_panel is fake_panel
    assert home.panel.IsShown() is False
    fake_panel.Show.assert_called()
    fake_panel.activate.assert_called_once()


def test_open_music_respects_disabled_setting(home):
    with (
        patch(
            "accessible_youtube_downloader_pro.settings_handler.config_get",
            return_value=False,
        ),
        patch("accessible_youtube_downloader_pro.speak") as speak,
    ):
        home.open_music()
    assert home.music_panel is None
    speak.assert_called_once()


def test_close_music_flips_back(home):
    fake_panel = MagicMock()
    with (
        patch("youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel),
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
        home.close_music()
    fake_panel.Hide.assert_called()
    assert home.panel.IsShown() is True
    home.musicBtn.SetFocus.assert_called()


def test_open_music_lazy_builds_once(home):
    fake_panel = MagicMock()
    with (
        patch(
            "youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel
        ) as ctor,
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
        home.close_music()
        home.open_music()
    ctor.assert_called_once()  # panel reused, not rebuilt


def test_open_music_sets_music_mode_flag(home):
    fake_panel = MagicMock()
    with (
        patch("youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel),
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
    assert home._in_music_mode is True


def test_close_music_clears_music_mode_flag(home):
    fake_panel = MagicMock()
    with (
        patch("youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel),
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
        home.close_music()
    assert home._in_music_mode is False


def test_restore_after_player_refocuses_music(home):
    fake_panel = MagicMock()
    with (
        patch("youtube_music.music_panel.YouTubeMusicPanel", return_value=fake_panel),
        patch("accessible_youtube_downloader_pro.speak"),
    ):
        home.open_music()
        # Simulate returning from the media player (frame reshown).
        home._restore_music_after_show()
    fake_panel.focus_list.assert_called()


def test_restore_after_player_noop_when_not_in_music(home):
    # Not in music mode: returning from a normal player must not touch music.
    home._in_music_mode = False
    home.music_panel = MagicMock()
    home._restore_music_after_show()
    home.music_panel.focus_list.assert_not_called()
