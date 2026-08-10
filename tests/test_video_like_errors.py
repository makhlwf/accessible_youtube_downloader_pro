from unittest.mock import patch

from utils import like_video


@patch("utils.ensure_deno_installed", return_value=False)
def test_like_video_missing_deno(mock_deno):
    res = like_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "like")
    assert res["success"] is False
    assert "Deno" in res["error"]


@patch("utils.ensure_deno_installed", return_value=True)
@patch("utils.ensure_cookies_configured", return_value=False)
def test_like_video_missing_cookies(mock_cookies, mock_deno):
    res = like_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "like")
    assert res["success"] is False
    assert "كوكيز" in res["error"] or "cookies" in res["error"].lower()
