import os
from http.cookiejar import Cookie
from unittest.mock import patch

import cookies_manager


def test_supported_browsers_map():
    assert "firefox" in cookies_manager.SUPPORTED_BROWSERS_MAP
    assert "chrome" in cookies_manager.SUPPORTED_BROWSERS_MAP
    assert "edge" in cookies_manager.SUPPORTED_BROWSERS_MAP
    assert "brave" in cookies_manager.SUPPORTED_BROWSERS_MAP


def test_cookie_to_netscape_line():
    cookie = Cookie(
        version=0,
        name="SAPISID",
        value="sample_token",
        port=None,
        port_specified=False,
        domain=".youtube.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=1893456000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )
    line = cookies_manager.cookie_to_netscape_line(cookie)
    assert (
        line.strip() == ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSAPISID\tsample_token"
    )


def test_get_installed_browsers():
    browsers = cookies_manager.get_installed_browsers()
    assert isinstance(browsers, list)
    assert len(browsers) > 0
    for b in browsers:
        assert "id" in b
        assert "name" in b


def test_extract_and_save_browser_cookies_success(tmp_path):
    target_file = str(tmp_path / "browser_cookies.txt")
    cookie = Cookie(
        version=0,
        name="LOGIN_INFO",
        value="test_val",
        port=None,
        port_specified=False,
        domain=".youtube.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=1893456000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )
    with patch(
        "cookies_manager._extract_cookies_from_browser_raw", return_value=[cookie]
    ):
        res = cookies_manager.extract_and_save_browser_cookies(
            "firefox", target_path=target_file
        )
        assert res["success"] is True
        assert res["count"] == 1
        assert res["path"] == target_file
        assert os.path.exists(target_file)
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "LOGIN_INFO" in content
            assert "# Netscape HTTP Cookie File" in content


def test_extract_and_save_browser_cookies_no_cookies_found(tmp_path):
    target_file = str(tmp_path / "browser_cookies.txt")
    with patch("cookies_manager._extract_cookies_from_browser_raw", return_value=[]):
        res = cookies_manager.extract_and_save_browser_cookies(
            "firefox", target_path=target_file
        )
        assert res["success"] is False
        assert "no_cookies" in res["error_type"]


def test_save_raw_browser_cookies_success(tmp_path):
    target_file = str(tmp_path / "browser_cookies.txt")
    raw_cookies = [
        {
            "domain": ".youtube.com",
            "name": "SAPISID",
            "value": "secret_val",
            "path": "/",
            "secure": True,
            "expirationDate": 1893456000,
        },
        {
            "domain": "example.com",
            "name": "unrelated",
            "value": "123",
            "path": "/",
        },
    ]
    res = cookies_manager.save_raw_browser_cookies(raw_cookies, target_path=target_file)
    assert res["success"] is True
    assert res["count"] == 1
    assert res["path"] == target_file
    assert os.path.exists(target_file)
    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "SAPISID" in content
        assert "secret_val" in content
        assert "# Netscape HTTP Cookie File" in content


def test_save_raw_browser_cookies_empty(tmp_path):
    target_file = str(tmp_path / "browser_cookies.txt")
    res = cookies_manager.save_raw_browser_cookies([], target_path=target_file)
    assert res["success"] is False
    assert res["error_type"] == "no_cookies"
