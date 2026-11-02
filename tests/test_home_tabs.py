"""Tests for the 5-tab HomeScreen UI arrangement and keyboard playback controls."""

from unittest.mock import MagicMock, patch

import pytest
import wx

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
        h = HomeScreen(start_hidden=True)
        yield h
        try:
            h.Destroy()
        except Exception:
            pass


def test_eight_tabs_structure(home):
    """Test that HomeScreen has a notebook with exactly 8 tabs in the correct order."""
    assert hasattr(home, "notebook")
    assert home.notebook.GetPageCount() == 8

    # Tab 0: Home page
    assert home.notebook.GetPage(0) is home.home_tab
    # Tab 1: Search tab
    assert home.notebook.GetPage(1) is home.search_tab
    # Tab 2: Operations tab
    assert home.notebook.GetPage(2) is home.ops_tab
    # Tab 3: Shorts tab
    assert home.notebook.GetPage(3) is home.shorts_tab
    # Tab 4: Subscriptions tab
    assert home.notebook.GetPage(4) is home.subs_tab
    # Tab 5: Watch History tab
    assert home.notebook.GetPage(5) is home.history_tab
    # Tab 6: Favorite videos tab
    assert home.notebook.GetPage(6) is home.fav_tab
    # Tab 7: YouTube Music tab
    assert home.notebook.GetPage(7) is home.music_tab


def test_operations_tab_content(home):
    """Test Operations tab combines URL input, playback, and download controls."""
    assert hasattr(home, "ops_url_ctrl")
    assert hasattr(home, "ops_paste_btn")
    assert hasattr(home, "ops_play_mode_radio")
    assert hasattr(home, "ops_play_btn")
    assert hasattr(home, "ops_download_format")
    assert hasattr(home, "ops_converting_format")
    assert hasattr(home, "ops_download_path")
    assert hasattr(home, "ops_change_path_btn")
    assert hasattr(home, "ops_download_btn")

    assert home.ops_url_ctrl.Parent is home.ops_tab
    assert home.ops_paste_btn.Parent is home.ops_tab
    assert home.ops_play_btn.Parent is home.ops_tab
    assert home.ops_download_btn.Parent is home.ops_tab


def test_operations_shortcuts_and_focus(home):
    """Test that onPlay (Ctrl+Y) and onDownload (Ctrl+D) switch to Operations tab and focus URL ctrl."""
    home.notebook.SetSelection(0)
    with (
        patch.object(home.ops_url_ctrl, "SetFocus") as mock_focus,
        patch.object(home.ops_url_ctrl, "SelectAll") as mock_select_all,
    ):
        home.onPlay()
        assert home.notebook.GetSelection() == 2
        mock_focus.assert_called_once()
        mock_select_all.assert_called_once()

    home.notebook.SetSelection(0)
    with (
        patch.object(home.ops_url_ctrl, "SetFocus") as mock_focus,
        patch.object(home.ops_url_ctrl, "SelectAll") as mock_select_all,
    ):
        home.onDownload()
        assert home.notebook.GetSelection() == 2
        mock_focus.assert_called_once()
        mock_select_all.assert_called_once()


def test_operations_paste_and_detect(home):
    """Test paste button and clipboard detection in Operations tab."""
    valid_yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with patch("pyperclip.paste", return_value=valid_yt):
        home.ops_url_ctrl.SetValue("")
        home.detect_ops_url_from_clipboard()
        assert home.ops_url_ctrl.GetValue() == valid_yt

        home.ops_url_ctrl.SetValue("")
        home.on_ops_paste()
        assert home.ops_url_ctrl.GetValue() == valid_yt


def test_operations_play_and_download_flow(home):
    """Test play and download from Operations tab."""
    # Invalid URL shows error
    home.ops_url_ctrl.SetValue("not a youtube link")
    with patch("accessible_youtube_downloader_pro.utils.show_error") as mock_err:
        home.on_ops_play()
        mock_err.assert_called_once()

    with patch("accessible_youtube_downloader_pro.utils.show_error") as mock_err:
        home.on_ops_download()
        mock_err.assert_called_once()

    # Valid URL calls play/download pipeline
    valid_yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    home.ops_url_ctrl.SetValue(valid_yt)

    with (
        patch(
            "accessible_youtube_downloader_pro.utils.check_yt_dlp", return_value=True
        ),
        patch("accessible_youtube_downloader_pro.LoadingDialog") as mock_dlg,
        patch("media_player.media_gui.MediaGui") as mock_media,
    ):
        fake_stream = MagicMock()
        fake_stream.title = "Test Video"
        mock_dlg.return_value.res = fake_stream
        home.on_ops_play(audio_mode=True)
        mock_media.assert_called_once()

    with (
        patch(
            "accessible_youtube_downloader_pro.utils.check_yt_dlp", return_value=True
        ),
        patch("download_handler.downloader.start_media_download") as mock_download,
    ):
        home.on_ops_download()
        mock_download.assert_called_once()


def test_home_page_tab_content(home):
    """Test that the first tab only has the home feed list and pagination button."""
    assert hasattr(home, "home_feed_list")
    assert hasattr(home, "load_more_home_button")
    assert home.home_feed_list.Parent is home.home_tab
    assert home.load_more_home_button.Parent is home.home_tab


def test_search_tab_content(home):
    """Test search tab has search query ctrl, filter box, results, and single play button."""
    assert hasattr(home, "search_query_ctrl")
    assert hasattr(home, "search_filter_box")
    assert hasattr(home, "search_submit_btn")
    assert hasattr(home, "search_suggestions_list")
    assert hasattr(home, "search_results_list")
    assert hasattr(home, "search_play_btn")
    assert hasattr(home, "search_download_btn")
    assert hasattr(home, "search_load_more_btn")

    assert home.search_query_ctrl.Parent is home.search_tab
    assert home.search_results_list.Parent is home.search_tab
    assert home.search_play_btn.Parent is home.search_tab


def test_ctrl_f_focuses_search_tab_and_query_ctrl(home):
    """Test that onSearch (Ctrl+F) selects the Search tab and focuses the query control."""
    home.notebook.SetSelection(0)
    assert home.notebook.GetSelection() == 0

    with (
        patch.object(home.search_query_ctrl, "SetFocus") as mock_focus,
        patch.object(home.search_query_ctrl, "SelectAll") as mock_select_all,
    ):
        home.onSearch()
        assert home.notebook.GetSelection() == 1
        mock_focus.assert_called_once()
        mock_select_all.assert_called_once()


def test_playback_respects_user_setting_and_ctrl_inversion(home):
    """Test get_effective_audio_mode respects defaultaudio (0=audio, 1=video) and invert=Ctrl."""
    # When user setting is 0 (Default to Audio)
    with patch(
        "accessible_youtube_downloader_pro.settings_handler.config_get",
        return_value=0,
    ):
        # Enter / normal: respects user setting -> Audio (True)
        assert home.get_effective_audio_mode(invert=False) is True
        # Ctrl+Enter: inverts user setting -> Video (False)
        assert home.get_effective_audio_mode(invert=True) is False

    # When user setting is 1 (Default to Video)
    with patch(
        "accessible_youtube_downloader_pro.settings_handler.config_get",
        return_value=1,
    ):
        # Enter / normal: respects user setting -> Video (False)
        assert home.get_effective_audio_mode(invert=False) is False
        # Ctrl+Enter: inverts user setting -> Audio (True)
        assert home.get_effective_audio_mode(invert=True) is True


def test_single_play_button_on_shorts_and_subs(home):
    """Test that separate audio/video buttons are replaced by single play buttons."""
    # Shorts tab: has play_shorts_btn, no separate play_shorts_audio_btn
    assert hasattr(home, "play_shorts_btn")
    assert not hasattr(home, "play_shorts_audio_btn")
    assert home.play_shorts_btn.Parent is home.shorts_tab

    # Subscriptions tab: has play_sub_btn, no separate play_sub_video_btn
    assert hasattr(home, "play_sub_btn")
    assert not hasattr(home, "play_sub_video_btn")
    assert home.play_sub_btn.Parent is home.subs_tab


def test_startup_focuses_notebook(home):
    """Test that running the app focuses the notebook so the focused tab gets focus."""
    with patch.object(home.notebook, "SetFocus") as mock_focus:
        event = MagicMock()
        home.checked = False
        with (
            patch(
                "accessible_youtube_downloader_pro.settings_handler.config_get",
                return_value=True,
            ),
            patch("accessible_youtube_downloader_pro.wx.CallAfter"),
        ):
            home.onShow(event)
            mock_focus.assert_called_once()


def test_shorts_tab_content_and_no_autoplay(home):
    """Test that Shorts tab has the list and play button, and does NOT start playing automatically."""
    assert hasattr(home, "shorts_list")
    assert hasattr(home, "play_shorts_btn")
    assert home.shorts_list.Parent is home.shorts_tab
    assert home.play_shorts_btn.Parent is home.shorts_tab
    assert home.shortsBtn is home.play_shorts_btn

    mock_shorts = [
        {
            "id": "short_1",
            "title": "Short One",
            "author": "Creator One",
            "url": "https://www.youtube.com/shorts/short_1",
        },
        {
            "id": "short_2",
            "title": "Short Two",
            "author": "Creator Two",
            "url": "https://www.youtube.com/shorts/short_2",
        },
    ]

    with (
        patch(
            "accessible_youtube_downloader_pro.utils.get_shorts_feed",
            return_value=mock_shorts,
        ),
        patch("media_player.media_gui.MediaGui") as mock_media_gui,
    ):
        home.on_open_shorts()
        home._update_shorts_feed(mock_shorts)

        mock_media_gui.assert_not_called()
        assert len(home.shorts_data) == 2
        assert home.shorts_list.GetCount() == 2


def test_subscriptions_tab_content(home):
    """Test subscriptions tab has feed list and button to open subscribed channels."""
    assert hasattr(home, "sub_feed_list")
    assert hasattr(home, "open_sub_channels_btn")
    assert home.sub_feed_list.Parent is home.subs_tab
    assert home.open_sub_channels_btn.Parent is home.subs_tab
    assert home.subscriptionsBtn is home.open_sub_channels_btn

    with patch("gui.subscriptions_dialog.SubscriptionsDialog") as mock_subs_dialog:
        home.on_open_subscriptions()
        mock_subs_dialog.assert_called_once_with(home)


def test_enter_and_ctrl_key_hooks(home):
    """Test that Enter and Ctrl+Enter on feed lists trigger playback with correct mode."""
    with (
        patch.object(home, "on_home_feed_play") as mock_home_play,
        patch.object(home, "on_play_short") as mock_short_play,
        patch.object(home, "on_play_sub_video") as mock_sub_play,
        patch.object(home, "on_play_search_result") as mock_search_play,
        patch.object(home, "on_ops_play") as mock_ops_play,
        patch.object(home, "on_play_history") as mock_history_play,
        patch.object(home, "on_play_favorite") as mock_fav_play,
        patch(
            "accessible_youtube_downloader_pro.settings_handler.config_get",
            return_value=0,
        ),
    ):
        # Enter key with Ctrl NOT down -> audio_mode=True (since defaultaudio=0)
        evt_enter = MagicMock()
        evt_enter.KeyCode = wx.WXK_RETURN
        evt_enter.ControlDown.return_value = False

        home.on_home_feed_hook(evt_enter)
        mock_home_play.assert_called_with(None, audio_mode=True)

        home.on_shorts_hook(evt_enter)
        mock_short_play.assert_called_with(audio_mode=True)

        home.on_sub_feed_hook(evt_enter)
        mock_sub_play.assert_called_with(audio_mode=True)

        home.on_search_results_hook(evt_enter)
        mock_search_play.assert_called_with(audio_mode=True)

        home.on_ops_url_hook(evt_enter)
        mock_ops_play.assert_called_with(audio_mode=True)

        home.on_history_list_hook(evt_enter)
        mock_history_play.assert_called_with(audio_mode=True)

        home.on_fav_list_hook(evt_enter)
        mock_fav_play.assert_called_with(audio_mode=True)

        # Enter key with Ctrl DOWN -> audio_mode=False (inverted)
        evt_ctrl_enter = MagicMock()
        evt_ctrl_enter.KeyCode = wx.WXK_RETURN
        evt_ctrl_enter.ControlDown.return_value = True

        home.on_home_feed_hook(evt_ctrl_enter)
        mock_home_play.assert_called_with(None, audio_mode=False)

        home.on_shorts_hook(evt_ctrl_enter)
        mock_short_play.assert_called_with(audio_mode=False)

        home.on_sub_feed_hook(evt_ctrl_enter)
        mock_sub_play.assert_called_with(audio_mode=False)

        home.on_search_results_hook(evt_ctrl_enter)
        mock_search_play.assert_called_with(audio_mode=False)

        home.on_ops_url_hook(evt_ctrl_enter)
        mock_ops_play.assert_called_with(audio_mode=False)

        home.on_history_list_hook(evt_ctrl_enter)
        mock_history_play.assert_called_with(audio_mode=False)

        home.on_fav_list_hook(evt_ctrl_enter)
        mock_fav_play.assert_called_with(audio_mode=False)


def test_history_tab_content(home):
    """Test Watch History tab controls, navigation, and playback."""
    assert hasattr(home, "history_list")
    assert hasattr(home, "history_play_btn")
    assert hasattr(home, "history_download_btn")
    assert hasattr(home, "history_fav_btn")
    assert hasattr(home, "load_more_history_btn")
    assert hasattr(home, "refresh_history_btn")

    assert home.history_list.Parent is home.history_tab
    assert home.history_play_btn.Parent is home.history_tab

    home.notebook.SetSelection(0)
    with (
        patch.object(home.history_list, "SetFocus") as mock_focus,
        patch.object(home, "load_history") as mock_load,
    ):
        home.onHistory()
        assert home.notebook.GetSelection() == 5
        mock_focus.assert_called_once()
        mock_load.assert_called_once()

    # Test updating history items
    fake_history = {
        "videos": [
            {
                "url": "https://www.youtube.com/watch?v=hist1",
                "title": "History Video 1",
                "author": "Channel 1",
            }
        ],
        "continuation": "token123",
    }
    home._update_history(fake_history)
    assert len(home.history_data) == 1
    assert home.history_list.GetCount() == 1
    assert home.load_more_history_btn.IsShown()

    # Play history item
    home.history_list.SetSelection(0)
    with (
        patch(
            "accessible_youtube_downloader_pro.utils.check_yt_dlp", return_value=True
        ),
        patch("accessible_youtube_downloader_pro.LoadingDialog") as mock_dlg,
        patch("media_player.media_gui.MediaGui") as mock_media,
    ):
        fake_stream = MagicMock()
        fake_stream.title = "History Video 1"
        mock_dlg.return_value.res = fake_stream
        home.on_play_history(audio_mode=True)
        mock_media.assert_called_once()


def test_favorites_tab_content(home):
    """Test Favorites tab controls, navigation, and operations."""
    assert hasattr(home, "fav_list")
    assert hasattr(home, "fav_play_btn")
    assert hasattr(home, "fav_download_btn")
    assert hasattr(home, "fav_delete_btn")
    assert hasattr(home, "fav_refresh_btn")

    assert home.fav_list.Parent is home.fav_tab
    assert home.fav_play_btn.Parent is home.fav_tab

    home.notebook.SetSelection(0)
    with (
        patch.object(home.fav_list, "SetFocus") as mock_focus,
        patch.object(home, "load_favorites") as mock_load,
    ):
        home.onFavorite()
        assert home.notebook.GetSelection() == 6
        mock_focus.assert_called_once()
        mock_load.assert_called_once()

    # Add mock row to favorites
    fake_fav = {
        "url": "https://www.youtube.com/watch?v=fav1",
        "title": "Favorite Video 1",
        "display_title": "Favorite Video 1. Channel 1",
        "live": 0,
        "channel_url": "",
        "channel_name": "Channel 1",
    }
    with patch.object(home.favorites, "get_all", return_value=[fake_fav]):
        home.load_favorites()
        assert len(home.fav_rows) == 1
        assert home.fav_list.GetCount() == 1

        home.fav_list.SetSelection(0)
        with (
            patch(
                "accessible_youtube_downloader_pro.utils.check_yt_dlp",
                return_value=True,
            ),
            patch("accessible_youtube_downloader_pro.LoadingDialog") as mock_dlg,
            patch("media_player.media_gui.MediaGui") as mock_media,
        ):
            fake_stream = MagicMock()
            fake_stream.title = "Favorite Video 1"
            mock_dlg.return_value.res = fake_stream
            home.on_play_favorite(audio_mode=False)
            mock_media.assert_called_once()
