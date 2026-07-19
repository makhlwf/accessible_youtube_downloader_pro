from unittest.mock import patch


def test_get_video_like_info_normalizes_count_and_rating():
    from utils import get_video_like_info

    with patch("utils.config_get", return_value="cookies.txt"), patch(
        "utils.deno_service"
    ) as mock_deno_service:
        mock_deno_service.send_command.return_value = {
            "likes": "1,234 likes",
            "is_liked": False,
            "is_disliked": True,
        }

        info = get_video_like_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert info == {
        "likes": 1234,
        "rating": "dislike",
        "is_liked": False,
        "is_disliked": True,
    }
    mock_deno_service.send_command.assert_called_once_with(
        "get_video_likes",
        {"cookiesPath": "cookies.txt", "videoId": "dQw4w9WgXcQ"},
    )


def test_get_video_likes_returns_none_on_service_error():
    from utils import get_video_likes

    with patch("utils.config_get", return_value=""), patch(
        "utils.deno_service"
    ) as mock_deno_service, patch("utils.YoutubeDL", None):
        mock_deno_service.send_command.return_value = {"error": "failed"}

        assert get_video_likes("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None


def test_get_video_like_info_falls_back_to_yt_dlp_count():
    import utils
    from utils import get_video_like_info

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {"like_count": 99}

    with patch("utils.config_get", return_value=""), patch(
        "utils.deno_service"
    ) as mock_deno_service, patch.object(utils, "YoutubeDL", FakeYoutubeDL):
        mock_deno_service.send_command.return_value = {"likes": None, "rating": "like"}

        info = get_video_like_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert info == {
        "likes": 99,
        "rating": "like",
        "is_liked": True,
        "is_disliked": False,
    }


def test_like_video_sends_remove_like_action():
    from utils import like_video

    with patch("utils.config_get", return_value="cookies.txt"), patch(
        "utils.os.path.exists", return_value=True
    ), patch("utils.deno_service") as mock_deno_service:
        mock_deno_service.send_command.return_value = {"success": True}

        assert (
            like_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "remove_like")
            is True
        )

    mock_deno_service.send_command.assert_called_once_with(
        "like_video",
        {
            "cookiesPath": "cookies.txt",
            "videoId": "dQw4w9WgXcQ",
            "action": "remove_like",
        },
    )
