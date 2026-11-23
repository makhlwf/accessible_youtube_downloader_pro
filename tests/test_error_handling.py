from unittest.mock import patch

from utils import (
    ensure_cookies_configured,
    ensure_deno_installed,
)


@patch("app_runtime.dependencies.paths.deno_path", "non_existent_deno.exe")
@patch("app_runtime.dependencies.paths.get_youtube_service_path", return_value=None)
@patch("app_runtime.dependencies.wx.MessageBox")
def test_ensure_deno_installed_missing(mock_msgbox, mock_service):
    mock_msgbox.return_value = 5  # wx.NO
    result = ensure_deno_installed(feature_name="الإعجاب")
    assert result is False
    assert mock_msgbox.called


@patch("youtube_backend.session.config_get")
@patch("youtube_backend.session.wx.MessageBox")
def test_ensure_cookies_configured_missing(mock_msgbox, mock_config_get):
    mock_config_get.return_value = None
    result = ensure_cookies_configured(feature_name="الإعجاب")
    assert result is False
    assert mock_msgbox.called
