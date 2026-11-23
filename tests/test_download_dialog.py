import sqlite3
import unittest
from unittest.mock import patch

import wx

import database
from download_handler.downloader import DownloadCancelled
from gui.download_dialog import DownloadDialog


class TestDownloadDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        database_patch = patch("database.con", connection)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        database.prepare_tables()

        # Mock settings_handler and utils to avoid side effects
        self.patcher_config_get = patch("gui.download_dialog.config_get")
        self.mock_config_get = self.patcher_config_get.start()

        def mock_get(key):
            if key == "path":
                return "C:\\test\\path"
            elif key == "defaultaudio":
                return "1"
            return ""

        self.mock_config_get.side_effect = mock_get

        self.patcher_config_set = patch("gui.download_dialog.config_set")
        self.mock_config_set = self.patcher_config_set.start()

        self.patcher_utils = patch("gui.download_dialog.utils")
        self.mock_utils = self.patcher_utils.start()
        self.mock_utils.is_supported_youtube_url.return_value = True
        self.mock_utils.check_yt_dlp.return_value = True

        self.patcher_start_media_download = patch(
            "gui.download_dialog.start_media_download"
        )
        self.mock_start_media_download = self.patcher_start_media_download.start()
        self.mock_start_media_download.return_value = True

        self.parent = wx.Frame(None)
        self.dialog = DownloadDialog(self.parent)

    def tearDown(self):
        if self.dialog:
            self.dialog.Destroy()
        self.patcher_config_get.stop()
        self.patcher_config_set.stop()
        self.patcher_utils.stop()
        self.patcher_start_media_download.stop()
        # wx.CallAfter causes issues if the app doesn't process events, so yield
        wx.Yield()

    def test_audio_choices(self):
        self.dialog.downloadingFormat.GetSelection.return_value = 0
        self.dialog.onRadioBox(wx.CommandEvent())

        choices = self.dialog.convertingFormat.GetItems()
        self.assertEqual(choices, ["m4a", "mp3", "wav", "flac"])
        self.assertEqual(
            self.dialog.convertingFormat.GetSelection(), 1
        )  # from defaultaudio="1"

    def test_video_choices(self):
        self.dialog.downloadingFormat.GetSelection.return_value = 1
        self.dialog.onRadioBox(wx.CommandEvent())

        choices = self.dialog.convertingFormat.GetItems()
        self.assertEqual(choices, ["mp4", "mkv"])
        self.assertEqual(self.dialog.convertingFormat.GetSelection(), 0)

    def test_onDownload_audio(self):
        self.dialog.videoLink.SetValue("https://youtube.com/watch?v=123")
        self.dialog.downloadingFormat.GetSelection.return_value = 0
        self.dialog.onRadioBox(wx.CommandEvent())
        self.dialog.convertingFormat.SetSelection(2)  # wav

        self.dialog.onDownload(wx.CommandEvent())

        self.mock_config_set.assert_called_with("defaultaudio", "2")
        self.mock_start_media_download.assert_called_once_with(
            "https://youtube.com/watch?v=123",
            "wav",
            self.parent,
            path="C:\\test\\path",
            folder=False,
        )

    def test_onDownload_video(self):
        self.dialog.videoLink.SetValue("https://youtube.com/watch?v=456")
        self.dialog.downloadingFormat.GetSelection.return_value = 1
        self.dialog.onRadioBox(wx.CommandEvent())
        self.dialog.convertingFormat.SetSelection(1)  # mkv

        self.dialog.onDownload(wx.CommandEvent())

        # defaultaudio should not be saved for video
        self.mock_config_set.assert_not_called()
        self.mock_start_media_download.assert_called_once_with(
            "https://youtube.com/watch?v=456",
            "mkv",
            self.parent,
            path="C:\\test\\path",
            folder=False,
        )

    def _queue_item(self, url, audio=True):
        self.dialog.videoLink.SetValue(url)
        self.dialog.downloadingFormat.GetSelection.return_value = 0 if audio else 1
        self.dialog.onRadioBox(wx.CommandEvent())
        self.dialog.on_add_to_queue(None)

    def test_queue_downloads_in_order_and_retains_failed_item(self):
        first = "https://youtu.be/abcdefghijk"
        second = "https://youtu.be/lmnopqrstuv"
        self._queue_item(first)
        self.dialog.path = "C:\\other"
        self._queue_item(second, audio=False)
        self.mock_start_media_download.assert_not_called()

        self.dialog.on_download_queue(None)
        self.dialog.on_download_queue(None)
        self.assertEqual(self.mock_start_media_download.call_count, 1)
        first_call = self.mock_start_media_download.call_args
        self.assertEqual(first_call.args[:2], (first, "mp3"))
        self.assertEqual(first_call.kwargs["path"], "C:\\test\\path")
        first_call.kwargs["on_finished"](RuntimeError("download failed"))

        second_call = self.mock_start_media_download.call_args
        self.assertEqual(second_call.args[:2], (second, "mp4"))
        self.assertEqual(second_call.kwargs["path"], "C:\\other")
        second_call.kwargs["on_finished"](0)
        self.assertEqual(self.mock_start_media_download.call_count, 2)
        self.assertEqual([item.url for item in self.dialog.queue], [first])
        self.assertTrue(self.dialog.download_queue.IsEnabled())

    def test_cancel_stops_queue_and_preserves_pending_downloads(self):
        self._queue_item("https://youtu.be/abcdefghijk")
        self._queue_item("https://youtu.be/lmnopqrstuv")
        self.dialog.on_download_queue(None)
        self.mock_start_media_download.call_args.kwargs["on_finished"](
            DownloadCancelled()
        )
        self.assertEqual(self.mock_start_media_download.call_count, 1)
        self.assertEqual(len(self.dialog.queue), 2)
        self.assertTrue(self.dialog.download_queue.IsEnabled())
        self.dialog.on_remove_from_queue(None)
        self.assertEqual(len(self.dialog.queue), 1)

    def test_reopening_shows_saved_queue_and_clear_removes_it(self):
        self._queue_item("https://youtu.be/abcdefghijk")
        self.dialog.Destroy()
        self.dialog = DownloadDialog(self.parent)
        self.assertEqual(self.dialog.queue_list.GetCount(), 1)
        with patch("wx.MessageBox", return_value=wx.YES):
            self.dialog.on_clear_queue(None)
        self.assertEqual(database.DownloadQueue.get_all(), [])
