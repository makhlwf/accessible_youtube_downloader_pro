from utils import (
    time_formatting,
    time_to_seconds,
    sanitize_filename,
    youtube_regexp,
    is_supported_youtube_url,
    extract_supported_youtube_url,
    extract_launch_youtube_url,
    format_duration,
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
        youtube_regexp("https://m.youtube.com/shorts/dQw4w9WgXcQ?si=test")
        is not None
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
    assert extract_launch_youtube_url(
        "hexplayer://open?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"
    ) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_launch_youtube_url(
        "hexplayer://open/https%3A%2F%2Fyoutu.be%2FdQw4w9WgXcQ"
    ) == "https://youtu.be/dQw4w9WgXcQ"
    assert extract_launch_youtube_url("hexplayer://open?url=https%3A%2F%2Fexample.com") == ""


def test_format_duration():
    assert "المدة:" in format_duration(60)
    assert format_duration(None) == "مباشر"
    assert "المدة:" in format_duration("01:00")
