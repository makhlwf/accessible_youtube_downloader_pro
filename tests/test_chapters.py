import unittest
from unittest.mock import patch


class TestVideoChapters(unittest.TestCase):
    @patch("utils.deno_service")
    @patch("utils.config_get")
    def test_get_video_chapters_success(self, mock_config_get, mock_deno_service):
        from utils import get_video_chapters

        mock_config_get.return_value = "fake/path/to/cookies"
        mock_deno_service.send_command.return_value = {
            "chapters": [
                {"title": "Chapter 1", "time_ms": 0},
                {"title": "Chapter 2", "time_ms": 60000},
            ]
        }

        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        chapters = get_video_chapters(url)

        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["title"], "Chapter 1")
        self.assertEqual(chapters[0]["time_ms"], 0)
        self.assertEqual(chapters[1]["title"], "Chapter 2")
        self.assertEqual(chapters[1]["time_ms"], 60000)

        mock_deno_service.send_command.assert_called_once_with(
            "get_video_chapters",
            {"cookiesPath": "fake/path/to/cookies", "videoId": "dQw4w9WgXcQ"},
        )

    @patch("utils.youtube_regexp")
    def test_get_video_chapters_invalid_url(self, mock_regexp):
        from utils import get_video_chapters

        mock_regexp.return_value = None
        url = "invalid_url"
        chapters = get_video_chapters(url)
        self.assertEqual(chapters, [])

    @patch("utils.deno_service")
    @patch("utils.config_get")
    def test_get_video_chapters_normalizes_alternate_time_fields(
        self, mock_config_get, mock_deno_service
    ):
        from utils import get_video_chapters

        mock_config_get.return_value = ""
        mock_deno_service.send_command.return_value = {
            "chapters": [
                {"title": "Later", "start_time": 60},
                {"title": "Intro", "time_range_start_millis": "0"},
            ]
        }

        chapters = get_video_chapters("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertEqual(
            chapters,
            [
                {"title": "Intro", "time_ms": 0},
                {"title": "Later", "time_ms": 60000},
            ],
        )

    @patch("utils.deno_service")
    @patch("utils.config_get")
    def test_get_video_chapters_falls_back_to_yt_dlp(
        self, mock_config_get, mock_deno_service
    ):
        from unittest.mock import patch

        import utils
        from utils import get_video_chapters

        calls = {}

        class FakeYoutubeDL:
            def __init__(self, opts):
                calls["opts"] = opts

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def extract_info(self, url, download=False):
                calls["url"] = url
                calls["download"] = download
                return {
                    "chapters": [
                        {"title": "Fallback", "start_time": 12.5},
                    ]
                }

        mock_config_get.return_value = ""
        mock_deno_service.send_command.return_value = {"chapters": []}

        with patch.object(utils, "YoutubeDL", FakeYoutubeDL):
            chapters = get_video_chapters("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertEqual(chapters, [{"title": "Fallback", "time_ms": 12500}])
        self.assertEqual(calls["download"], False)
        self.assertTrue(calls["opts"]["skip_download"])
