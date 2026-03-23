from utils import (
    time_formatting,
    time_to_seconds,
    sanitize_filename,
    youtube_regexp,
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
    assert youtube_regexp("not a youtube link") is None


def test_format_duration():
    assert "المدة:" in format_duration(60)
    assert format_duration(None) == "مباشر"
    assert "المدة:" in format_duration("01:00")
