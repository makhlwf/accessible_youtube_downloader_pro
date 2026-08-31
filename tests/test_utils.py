import utils
from utils import (
    extract_launch_youtube_url,
    extract_supported_youtube_url,
    format_duration,
    is_supported_youtube_url,
    sanitize_filename,
    time_formatting,
    time_to_seconds,
    youtube_regexp,
)


def test_time_formatting():
    assert time_formatting(0) == "0 ثانية"
    assert time_formatting(1) == "ثانية واحدة"
    assert time_formatting(2) == "ثانيتين"
    assert "3 ثواني" in time_formatting(3)
    assert "11 ثانية" in time_formatting(11)
    assert "دقيقة واحدة" in time_formatting(60)
    assert "ساعة واحدة" in time_formatting(3600)
    assert "ساعتان" in time_formatting(7200)
    assert time_formatting(None) == ""


def test_time_to_seconds():
    assert time_to_seconds("01:00") == 60
    assert time_to_seconds("1:00:00") == 3600
    assert time_to_seconds("30") == 30
    assert time_to_seconds("invalid") is None
    assert time_to_seconds(None) is None


def test_sanitize_filename():
    assert sanitize_filename("hello/world") == "hello_world"
    assert sanitize_filename("file?name*") == "file_name_"
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename(None) == "unnamed"


def test_youtube_regexp():
    assert youtube_regexp("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is not None
    assert youtube_regexp("https://youtu.be/dQw4w9WgXcQ") is not None
    assert (
        youtube_regexp("https://www.youtube.com/watch?feature=shared&v=dQw4w9WgXcQ")
        is not None
    )
    assert (
        youtube_regexp("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared")
        is not None
    )
    assert youtube_regexp("https://www.youtube.com/embed/dQw4w9WgXcQ") is not None
    assert youtube_regexp("https://www.youtube.com/v/dQw4w9WgXcQ") is not None
    assert youtube_regexp("https://www.youtube.com/shorts/dQw4w9WgXcQ") is not None
    assert (
        youtube_regexp("https://youtube.com/shorts/dQw4w9WgXcQ?feature=share")
        is not None
    )
    assert (
        youtube_regexp("https://m.youtube.com/shorts/dQw4w9WgXcQ?si=test") is not None
    )
    assert youtube_regexp("not a youtube link") is None


def test_is_supported_youtube_url():
    assert is_supported_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_supported_youtube_url("https://youtu.be/dQw4w9WgXcQ")
    assert is_supported_youtube_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_supported_youtube_url("https://www.youtube.com/playlist?list=PL123")
    assert is_supported_youtube_url("https://www.youtube.com/channel/UC12345678901")
    assert is_supported_youtube_url("https://www.youtube.com/@HexPlayer")
    assert not is_supported_youtube_url("https://www.youtube.com/")
    assert not is_supported_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")


def test_extract_supported_youtube_url():
    text = "open https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared now"
    assert (
        extract_supported_youtube_url(text)
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared"
    )
    assert extract_supported_youtube_url("youtube.com/playlist?list=PL123") == (
        "https://youtube.com/playlist?list=PL123"
    )
    assert extract_supported_youtube_url("no link here") == ""


def test_extract_launch_youtube_url():
    assert (
        extract_launch_youtube_url(
            "hexplayer://open?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"
        )
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert (
        extract_launch_youtube_url(
            "hexplayer://open/https%3A%2F%2Fyoutu.be%2FdQw4w9WgXcQ"
        )
        == "https://youtu.be/dQw4w9WgXcQ"
    )
    assert (
        extract_launch_youtube_url("hexplayer://open?url=https%3A%2F%2Fexample.com")
        == ""
    )


def test_format_duration():
    assert "المدة:" in format_duration(60)
    assert format_duration(None) == "مباشر"
    assert "المدة:" in format_duration("01:00")


def test_get_watch_history_returns_local_history_without_cookies(monkeypatch):
    deno_calls = []
    cookie_calls = []
    monkeypatch.setattr(
        utils, "ensure_deno_installed", lambda **kw: deno_calls.append(kw) or True
    )
    monkeypatch.setattr(
        utils,
        "ensure_cookies_configured",
        lambda **kw: cookie_calls.append(kw) or False,
    )
    monkeypatch.setattr(
        utils,
        "_local_watch_history_response",
        lambda continuation=None, error=None: {
            "videos": [{"title": "Local Video"}],
            "continuation": None,
            "source": "local",
            "error": error,
        },
    )

    result = utils.get_watch_history()

    assert len(deno_calls) == 1
    assert len(cookie_calls) == 1
    assert result["videos"][0]["title"] == "Local Video"
    assert result["source"] == "local"
    assert "error" in result
    assert "عذراً، يتطلب عرض سجل يوتيوب أونلاين" in result["error"]


def test_get_watch_history_falls_back_to_local_on_cookie_error(monkeypatch):
    deno_calls = []
    cookie_calls = []
    monkeypatch.setattr(
        utils, "ensure_deno_installed", lambda **kw: deno_calls.append(kw) or True
    )
    monkeypatch.setattr(
        utils, "ensure_cookies_configured", lambda **kw: cookie_calls.append(kw) or True
    )
    monkeypatch.setattr(utils, "config_get", lambda key: "cookies.txt")
    monkeypatch.setattr(utils.os.path, "exists", lambda path: True)
    monkeypatch.setattr(
        utils.deno_service,
        "send_command",
        lambda command, params: {"error": "Not logged in"},
    )
    monkeypatch.setattr(
        utils,
        "_local_watch_history_response",
        lambda continuation=None, error=None: {
            "videos": [{"title": "Fallback Video"}],
            "continuation": None,
            "source": "local",
        },
    )

    result = utils.get_watch_history()

    assert len(deno_calls) == 1
    assert len(cookie_calls) == 1
    assert result["videos"][0]["title"] == "Fallback Video"
    assert result["source"] == "local"


def test_update_watch_history_stores_local_history_without_cookies(monkeypatch):
    calls = []

    class FakeWatchHistory:
        @classmethod
        def add_or_update(cls, data):
            calls.append(data)

    monkeypatch.setattr(utils, "WatchHistory", FakeWatchHistory)
    monkeypatch.setattr(utils, "config_get", lambda key: "")
    monkeypatch.setattr(
        utils.deno_service,
        "send_command",
        lambda command, params: (_ for _ in ()).throw(
            AssertionError("Deno should not be called without cookies")
        ),
    )

    utils.update_watch_history(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        watched_seconds=12.5,
        title="Played Video",
        channel_name="Channel",
    )

    assert calls == [
        {
            "title": "Played Video",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "channel_name": "Channel",
            "channel_url": "",
            "is_live": False,
            "watched_seconds": 12.5,
        }
    ]


def test_get_windows_region():
    region = utils.get_windows_region()
    assert isinstance(region, str)
    assert len(region) == 2
    assert region.isupper()
    assert region.isalpha()


def test_get_windows_region_mocked(monkeypatch):
    class FakeBuf:
        value = "de"

    monkeypatch.setattr(utils.os, "name", "nt")
    monkeypatch.setattr(
        "ctypes.windll.kernel32.GetUserDefaultGeoName",
        lambda buf, size: setattr(buf, "value", "DE") or 2,
    )
    assert utils.get_windows_region() == "DE"


def test_update_watch_history_uses_deno_service_when_cookies_present(
    monkeypatch, tmp_path
):
    calls = []
    deno_calls = []

    class FakeWatchHistory:
        @classmethod
        def add_or_update(cls, data):
            calls.append(data)

    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")

    monkeypatch.setattr(utils, "WatchHistory", FakeWatchHistory)
    monkeypatch.setattr(utils, "config_get", lambda key: str(cookie_file))
    monkeypatch.setattr(
        utils.deno_service,
        "send_command",
        lambda command, params: (
            deno_calls.append((command, params)) or {"success": True}
        ),
    )

    utils.update_watch_history(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        watched_seconds=42.0,
        title="Sample Video",
        channel_name="Sample Author",
    )

    assert len(calls) == 1
    assert len(deno_calls) == 1
    assert deno_calls[0][0] == "update_watch_history"
    assert deno_calls[0][1]["videoId"] == "dQw4w9WgXcQ"
    assert deno_calls[0][1]["watchedSeconds"] == "42.0"


def test_info_cache_bounded_lru_and_expiration():
    cache = utils.InfoCache(default_ttl=10, maxsize=3)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")

    assert cache.get("k1") == "v1"
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"

    # Adding a 4th key should evict the oldest accessed key (k1 was accessed before k2 and k3, so k1's access moved it to end)
    # Access k1 and k2 to make k3 the oldest
    cache.get("k1")
    cache.get("k2")
    cache.set("k4", "v4")

    assert cache.get("k3") is None
    assert cache.get("k1") == "v1"
    assert cache.get("k2") == "v2"
    assert cache.get("k4") == "v4"
    assert len(cache.cache) <= 3

    # Clear method
    cache.clear()
    assert len(cache.cache) == 0
    assert cache.get("k1") is None
