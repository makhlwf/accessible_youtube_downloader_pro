"""Tests for youtube_music.adapters — payload normalisation + result protocol."""

from youtube_music import adapters
from youtube_music.adapters import YTMusicResult, normalize_item, normalize_items


def test_normalize_song():
    item = {
        "videoId": "abc123",
        "title": "My Song",
        "artists": [{"name": "Artist One", "id": "UCchan"}],
        "album": {"name": "The Album", "id": "MPREalb"},
        "duration": "3:45",
        "views": "1M",
    }
    row = normalize_item(item)
    assert row["type"] == "song"
    assert row["videoId"] == "abc123"
    assert row["title"] == "My Song"
    assert row["subtitle"] == "Artist One"
    assert row["channel"] == {
        "name": "Artist One",
        "url": "https://www.youtube.com/channel/UCchan",
    }
    assert row["duration"] == "3:45"


def test_normalize_album_by_browse_prefix():
    item = {"title": "An Album", "browseId": "MPREb_xyz", "artists": []}
    assert normalize_item(item)["type"] == "album"


def test_normalize_artist_by_channel_prefix():
    item = {"title": "An Artist", "browseId": "UC_artist"}
    assert normalize_item(item)["type"] == "artist"


def test_normalize_playlist():
    item = {"title": "A Playlist", "playlistId": "PL123"}
    row = normalize_item(item)
    assert row["type"] == "playlist"
    assert row["playlistId"] == "PL123"


def test_normalize_uses_explicit_result_type():
    item = {"title": "X", "videoId": "v", "resultType": "video"}
    assert normalize_item(item)["type"] == "video"
    assert normalize_item({"title": "s", "resultType": "single"})["type"] == "album"


def test_normalize_preserves_set_video_id():
    item = {"videoId": "v1", "setVideoId": "set789", "title": "t"}
    assert normalize_item(item)["setVideoId"] == "set789"


def test_normalize_rejects_non_dict():
    assert normalize_item("nope") is None
    assert normalize_item(None) is None


def test_normalize_items_drops_bad_entries():
    rows = normalize_items([{"title": "ok", "videoId": "v"}, None, 42])
    assert len(rows) == 1


def test_normalize_handles_missing_fields():
    row = normalize_item({})
    assert row["title"] == ""
    assert row["videoId"] is None
    assert row["channel"] == {"name": "", "url": ""}
    assert row["type"] == "unknown"


def test_single_artist_string_form():
    row = normalize_item({"title": "t", "artist": "Solo", "videoId": "v"})
    assert row["subtitle"] == "Solo"


def test_result_protocol():
    rows = [
        {
            "videoId": "v1",
            "title": "One",
            "channel": {"name": "C", "url": "u"},
            "views": "5",
        },
        {"videoId": "v2", "title": "Two"},
    ]
    result = YTMusicResult(rows)
    assert len(result) == 2
    assert result.get_url(0) == "https://www.youtube.com/watch?v=v1"
    assert result.get_title(1) == "Two"
    assert result.get_type(0) == "video"
    assert result.get_channel(0) == {"name": "C", "url": "u"}
    assert result.get_channel(1) == {"name": "", "url": ""}
    # stream slotting mirrors stream_key(audio_mode)
    result.set_stream(0, "STREAM", audio_mode=True)
    assert result.get_stream(0, audio_mode=True) == "STREAM"
    assert result.get_stream(0, audio_mode=False) is None
    hist = result.get_history_data(0)
    assert hist["url"] == "https://www.youtube.com/watch?v=v1"
    assert hist["channel_name"] == "C"


def test_result_playable_only_skips_non_videos():
    rows = [
        {"videoId": "v1", "title": "song"},
        {"browseId": "MPREx", "title": "album"},
        {"playlistId": "PL", "title": "pl"},
    ]
    result = YTMusicResult.playable_only(rows)
    assert len(result) == 1
    assert result.get_url(0).endswith("v=v1")


def test_display_title_formats():
    assert (
        adapters.display_title({"title": "T", "subtitle": "A", "duration": "2:00"})
        == "T - A (2:00)"
    )
    assert adapters.display_title({"title": "Solo"}) == "Solo"
