from unittest.mock import patch

import pytest

from utils import like_video


@patch("youtube_backend.metadata.ensure_deno_installed", return_value=False)
def test_like_video_missing_deno(mock_deno):
    res = like_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "like")
    assert res["success"] is False
    assert "Deno" in res["error"]


@patch("youtube_backend.metadata.ensure_deno_installed", return_value=True)
@patch("youtube_backend.metadata.ensure_cookies_configured", return_value=False)
def test_like_video_missing_cookies(mock_cookies, mock_deno):
    res = like_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "like")
    assert res["success"] is False
    assert "كوكيز" in res["error"] or "cookies" in res["error"].lower()


@pytest.mark.parametrize("action", ["like", "dislike", "remove_like"])
@patch("youtube_backend.metadata.get_windows_region", return_value="US")
@patch("youtube_backend.metadata.deno_service.send_command", return_value={"success": True})
def test_reaction_uses_video_id_even_when_watch_url_contains_playlist(
    send, region, action
):
    url = "https://www.youtube.com/watch?list=PL12345678901234&v=dQw4w9WgXcQ"
    assert like_video(url, action, cookies_path="test-cookie-file")["success"]
    send.assert_called_once_with(
        "like_video",
        {
            "videoId": "dQw4w9WgXcQ",
            "action": action,
            "cookiesPath": "test-cookie-file",
            "location": "US",
        },
    )
