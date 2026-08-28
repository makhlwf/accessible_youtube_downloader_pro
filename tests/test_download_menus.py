from unittest.mock import ANY, MagicMock, patch

import pytest

from gui.channel_dialog import ChannelDialog
from gui.favorites import Favorites
from gui.history import HistoryDialog
from gui.playlist_dialog import PlaylistDialog
from media_player.media_gui import MediaGui
from youtube_browser.browser import YoutubeBrowser


@pytest.fixture
def mock_downloader():
    with patch("download_handler.downloader.start_media_download") as mock_start:
        yield mock_start


def test_browser_download_menu_formats(mock_downloader):
    browser = MagicMock()
    browser.searchResults.Selection = 0
    browser.search.get_url.return_value = "http://test"
    browser.search.get_title.return_value = "Test Title"
    browser.search.get_type.return_value = "video"

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("youtube_browser.browser.LoadingDialog") as ld,
    ):
        ld.return_value.res = None

        YoutubeBrowser.onDownload(browser, None)

        YoutubeBrowser.onVideoDownload(browser, MagicMock(), "mp4")
        browser._download_media.assert_called_with(
            "mp4", "http://test", ANY, "video", title="Test Title", quality=None
        )


def test_media_gui_download_menu_formats(mock_downloader):
    gui = MagicMock()
    gui.url = "http://test"
    gui.title = "Test Title"
    gui.path = "C:\\path"

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("media_player.media_gui.LoadingDialog") as ld,
    ):
        ld.return_value.res = None

        # media_gui creates its download menu in contextSetup, so no onDownload
        MediaGui.onVideoDownload(gui, MagicMock(), "mkv")
        gui._download_media.assert_called_with(
            "mkv", "http://test", ANY, path="C:\\path", quality=None
        )


def test_channel_dialog_download_menu_formats(mock_downloader):
    dialog = MagicMock()
    dialog.current_selection.return_value = 0
    dialog.current_result.get_url.return_value = "http://video"
    dialog.current_result.get_title.return_value = "Video Title"
    dialog.current_result.get_type.return_value = "video"

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("gui.channel_dialog.LoadingDialog") as ld,
    ):
        ld.return_value.res = None
        ChannelDialog.onDownload(dialog, None)

        ChannelDialog.onVideoDownload(dialog, MagicMock(), "mp4")
        dialog._download_media.assert_called_with(
            "mp4", "http://video", ANY, "video", title="Video Title", quality=None
        )

        ChannelDialog.onAudioDownload(dialog, MagicMock(), "mp3")
        dialog._download_current.assert_called_with("mp3")


def test_playlist_dialog_download_menu_formats(mock_downloader):
    dialog = MagicMock()
    dialog.videosBox.Selection = 0
    dialog.result.get_id.return_value = "video_id"
    dialog.result.get_title.return_value = "Video Title"
    dialog.title = "Playlist Title"

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("gui.playlist_dialog.LoadingDialog") as ld,
        patch("gui.playlist_dialog.config_get", return_value="C:\\path"),
    ):
        ld.return_value.res = None
        PlaylistDialog.onDownload(dialog, None)

        PlaylistDialog.onVideoDownload(dialog, MagicMock(), "mkv")
        dialog._download_media.assert_called()

        PlaylistDialog.onAudioDownload(dialog, MagicMock(), "wav")
        dialog._download_media.assert_called()


def test_history_download_menu_formats(mock_downloader):
    dialog = MagicMock()
    dialog.historyList.GetSelection.return_value = 0
    dialog.history_data = [
        {"url": "http://history_vid", "title": "History Title", "author": "Author"}
    ]

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("gui.history.LoadingDialog") as ld,
    ):
        ld.return_value.res = None
        HistoryDialog.onDownload(dialog, None)

        HistoryDialog.onVideoDownload(dialog, MagicMock(), "mp4")
        dialog._download_media.assert_called()

        HistoryDialog.onAudioDownload(dialog, MagicMock(), "flac")
        dialog._download_media.assert_called()


def test_favorites_download_menu_formats(mock_downloader):
    dialog = MagicMock()
    dialog.favList.Selection = 0
    dialog.rows = [
        {
            "url": "http://fav_vid",
            "title": "Fav Title",
            "display_title": "Fav Title. Author",
            "live": 0,
            "channel_url": "",
            "channel_name": "",
        }
    ]

    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("gui.favorites.LoadingDialog") as ld,
    ):
        ld.return_value.res = None
        Favorites.onDownload(dialog, None)

        Favorites.onVideoDownload(dialog, MagicMock(), "mkv")
        dialog._download_media.assert_called()

        Favorites.onAudioDownload(dialog, MagicMock(), "m4a")
        dialog._download_media.assert_called()
