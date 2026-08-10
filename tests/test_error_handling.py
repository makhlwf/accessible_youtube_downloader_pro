from unittest.mock import patch

from utils import (
    ensure_cookies_configured,
    ensure_deno_installed,
    format_bilingual_message,
)


def test_format_bilingual_message():
    msg = format_bilingual_message("خطأ في الاتصال", "Connection error")
    assert msg == "خطأ في الاتصال\nConnection error"


@patch("utils.paths.deno_path", "non_existent_deno.exe")
@patch("utils.wx.MessageBox")
def test_ensure_deno_installed_missing(mock_msgbox):
    mock_msgbox.return_value = 5  # wx.NO
    result = ensure_deno_installed(feature_name_ar="الإعجاب", feature_name_en="liking")
    assert result is False
    assert mock_msgbox.called


@patch("utils.config_get")
@patch("utils.wx.MessageBox")
def test_ensure_cookies_configured_missing(mock_msgbox, mock_config_get):
    mock_config_get.return_value = None
    result = ensure_cookies_configured(
        feature_name_ar="الإعجاب", feature_name_en="liking"
    )
    assert result is False
    assert mock_msgbox.called
