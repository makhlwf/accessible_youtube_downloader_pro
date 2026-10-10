"""Tests for youtube_music.auth_bridge — cookie parsing and header building.

Covers the happy path plus worst cases: missing file, unreadable file, no auth
cookies (anonymous), SAPISID synthesis, youtube.com precedence, malformed lines,
and that cookie values are not emitted into logs.
"""

import logging

from youtube_music import auth_bridge

HEADER = "# Netscape HTTP Cookie File\n# http://curl.haxx.se/rfc/cookie_spec.html\n\n"


def _write(tmp_path, lines):
    path = tmp_path / "cookies.txt"
    path.write_text(HEADER + "".join(lines), encoding="utf-8")
    return str(path)


def _line(domain, name, value, flag="TRUE", path="/", secure="TRUE", expires="0"):
    return f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"


def test_missing_file_returns_empty(tmp_path):
    missing = str(tmp_path / "nope.txt")
    assert auth_bridge.parse_netscape_cookies(missing) == {}
    assert auth_bridge.is_authenticated(missing) is False
    assert auth_bridge.build_browser_headers(missing) is None


def test_no_auth_cookies_is_anonymous(tmp_path):
    path = _write(tmp_path, [_line(".youtube.com", "PREF", "f1=40000000")])
    assert auth_bridge.is_authenticated(path) is False
    assert auth_bridge.build_browser_headers(path) is None


def test_auth_cookies_build_headers(tmp_path):
    path = _write(
        tmp_path,
        [
            _line(".youtube.com", "SAPISID", "secret_sapisid"),
            _line(".youtube.com", "__Secure-3PAPISID", "secret_3papisid"),
            _line(".youtube.com", "LOGIN_INFO", "token"),
        ],
    )
    assert auth_bridge.is_authenticated(path) is True
    headers = auth_bridge.build_browser_headers(path)
    assert headers is not None
    assert "SAPISID=secret_sapisid" in headers["Cookie"]
    assert headers["x-origin"] == "https://music.youtube.com"
    assert headers["X-Goog-AuthUser"] == "0"
    # ytmusicapi detects browser auth via a SAPISIDHASH Authorization sentinel,
    # then recomputes the real hash per request.
    assert "SAPISIDHASH" in headers["Authorization"]


def test_sapisid_synthesised_from_3papisid(tmp_path):
    path = _write(tmp_path, [_line(".youtube.com", "__Secure-3PAPISID", "abc123")])
    cookie_map = auth_bridge.parse_netscape_cookies(path)
    assert cookie_map["SAPISID"] == "abc123"
    # __Secure-3PAPISID alone counts as authenticated.
    assert auth_bridge.is_authenticated(path) is True


def test_youtube_domain_takes_precedence(tmp_path):
    # Same cookie name on two domains; the youtube.com value must win.
    path = _write(
        tmp_path,
        [
            _line(".google.com", "SAPISID", "google_value"),
            _line(".youtube.com", "SAPISID", "youtube_value"),
        ],
    )
    cookie_map = auth_bridge.parse_netscape_cookies(path)
    assert cookie_map["SAPISID"] == "youtube_value"


def test_malformed_lines_are_skipped(tmp_path):
    path = _write(
        tmp_path,
        [
            "not\ta\tvalid\tline\n",  # < 7 fields
            _line(".youtube.com", "SID", "sid_value"),
            "\t\t\t\t\t\t\n",  # empty name
        ],
    )
    cookie_map = auth_bridge.parse_netscape_cookies(path)
    assert cookie_map == {"SID": "sid_value"}
    assert auth_bridge.is_authenticated(path) is True


def test_cookie_values_not_logged(tmp_path, caplog):
    path = _write(tmp_path, [_line(".youtube.com", "SAPISID", "TOPSECRETVALUE")])
    with caplog.at_level(logging.DEBUG, logger="youtube_music.auth_bridge"):
        auth_bridge.build_browser_headers(path)
    assert "TOPSECRETVALUE" not in caplog.text


def test_unreadable_file_returns_empty(tmp_path, monkeypatch):
    path = _write(tmp_path, [_line(".youtube.com", "SID", "x")])

    def boom(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("builtins.open", boom)
    assert auth_bridge.parse_netscape_cookies(path) == {}
    assert auth_bridge.build_browser_headers(path) is None


def test_none_path_resolves_default(monkeypatch):
    # When no path is given, the app's default cookie file is consulted.
    import youtube_music.auth_bridge as ab

    monkeypatch.setattr(ab, "_resolve_path", lambda p: "" if p is None else p)
    assert ab.parse_netscape_cookies(None) == {}
    assert ab.is_authenticated(None) is False
