import unittest
from unittest.mock import patch

import wx

from gui.download_dialog import DownloadDialog


class TestDownloadDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()

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

        self.dialog = DownloadDialog(None)

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
            self.dialog,
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
            self.dialog,
            path="C:\\test\\path",
            folder=False,
        )
