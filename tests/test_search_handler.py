import pytest
from unittest.mock import AsyncMock, patch
from youtube_browser.search_handler import (
    ChannelTabResult,
    PlaylistResult,
    SimpleResult,
    Search,
)


@pytest.mark.asyncio
async def test_playlist_result_init_async():
    url = "https://youtube.com/playlist?list=123"
    playlist_data = {
        "title": "Test Playlist",
        "videos": [
            {
                "id": "vid1",
                "title": "Video 1",
                "link": "https://youtube.com/watch?v=vid1",
                "duration": "01:00",
                "channel": {
                    "name": "Channel 1",
                    "link": "https://youtube.com/channel/c1",
                },
            }
        ],
    }

    with patch("youtube_browser.search_handler.Playlist") as MockPlaylist:
        MockPlaylist.getVideos = AsyncMock(return_value=playlist_data)

        res = PlaylistResult(url)
        await res.init_async()

        assert res.title == "Test Playlist"
        assert len(res.videos) == 1
        assert res.videos[0]["title"] == "Video 1"
        assert res.get_url(0) == "https://youtube.com/watch?v=vid1"


@pytest.mark.asyncio
async def test_playlist_result_falls_back_to_yt_dlp(monkeypatch):
    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "title": "Fallback Playlist",
                "entries": [
                    {
                        "id": "fallback1",
                        "title": "Fallback Video",
                        "url": "fallback1",
                        "duration": 90,
                        "channel": "Fallback Channel",
                        "channel_url": "https://youtube.com/channel/fallback",
                    }
                ],
            }

    monkeypatch.setattr("youtube_browser.search_handler.utils.YoutubeDL", FakeYDL)

    with patch("youtube_browser.search_handler.Playlist") as MockPlaylist:
        MockPlaylist.getVideos = AsyncMock(side_effect=TypeError("bad playlist"))

        res = PlaylistResult("https://youtube.com/playlist?list=123")
        await res.init_async()

        assert res.title == "Fallback Playlist"
        assert res.count == 1
        assert res.get_url(0) == "https://www.youtube.com/watch?v=fallback1"
        assert res.get_channel(0)["url"] == "https://youtube.com/channel/fallback"


def test_simple_result():
    data = [{"url": "url1", "title": "Title 1", "type": "video"}]
    res = SimpleResult(data)
    assert len(res) == 1
    assert res.get_url(0) == "url1"
    assert res.get_title(0) == "Title 1"
    assert res.get_type(0) == "video"


def test_stream_cache_is_mode_specific():
    data = [{"url": "url1", "title": "Title 1", "type": "video"}]
    simple = SimpleResult(data)
    simple.set_stream(0, "audio", audio_mode=True)
    simple.set_stream(0, "video", audio_mode=False)
    assert simple.get_stream(0, audio_mode=True) == "audio"
    assert simple.get_stream(0, audio_mode=False) == "video"

    playlist = PlaylistResult("https://youtube.com/playlist?list=123")
    playlist.videos = [{"url": "url1"}]
    playlist.set_stream(0, "audio", audio_mode=True)
    playlist.set_stream(0, "video", audio_mode=False)
    assert playlist.get_stream(0, audio_mode=True) == "audio"
    assert playlist.get_stream(0, audio_mode=False) == "video"


@pytest.mark.asyncio
async def test_search_init_async():
    query = "test"
    search_result = {
        "result": [
            {
                "title": "Search Result 1",
                "link": "https://youtube.com/watch?v=sr1",
                "duration": 120,
                "viewCount": {"short": "100 views"},
                "channel": {
                    "name": "Channel 1",
                    "link": "https://youtube.com/channel/c1",
                },
            }
        ]
    }

    with patch("youtube_browser.search_handler.VideosSearch") as MockVideosSearch:
        mock_search_instance = MockVideosSearch.return_value
        mock_search_instance.next = AsyncMock(return_value=search_result)

        search = Search(query)
        await search.init_async()

        assert search.count == 1
        assert search.get_title(0) == "Search Result 1"
        assert search.get_url(0) == "https://youtube.com/watch?v=sr1"
        search.set_stream(0, "audio", audio_mode=True)
        search.set_stream(0, "video", audio_mode=False)
        assert search.get_stream(0, audio_mode=True) == "audio"
        assert search.get_stream(0, audio_mode=False) == "video"


@pytest.mark.asyncio
async def test_channel_search_init_async():
    search_result = {
        "result": [
            {
                "type": "channel",
                "id": "UC123",
                "title": "Test Channel",
                "videoCount": "12",
                "subscribers": "1.2K subscribers",
                "link": "https://www.youtube.com/channel/UC123",
            }
        ]
    }

    with patch("youtube_browser.search_handler.ChannelsSearch") as MockChannelsSearch:
        mock_search_instance = MockChannelsSearch.return_value
        mock_search_instance.next = AsyncMock(return_value=search_result)

        search = Search("test", filter=5)
        await search.init_async()

        assert search.count == 1
        assert search.get_type(0) == "channel"
        assert search.get_url(0) == "https://www.youtube.com/channel/UC123"
        assert "قناة" in search.get_titles()[0]
        assert "1.2K subscribers" in search.get_titles()[0]


def test_channel_tab_result_normalizes_video_entries(monkeypatch):
    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "title": "Test Channel",
                "entries": [
                    {
                        "id": "abc123",
                        "title": "Video 1",
                        "url": "abc123",
                        "duration": "01:00",
                        "channel": "Test Channel",
                        "channel_url": "https://www.youtube.com/channel/UC123",
                        "view_count": 42,
                    }
                ],
            }

    monkeypatch.setattr("youtube_browser.search_handler.utils.YoutubeDL", FakeYDL)

    result = ChannelTabResult(
        "https://www.youtube.com/channel/UC123/videos", "videos", "Test Channel"
    )

    assert result.count == 1
    assert result.get_type(0) == "video"
    assert result.get_url(0) == "https://www.youtube.com/watch?v=abc123"
    assert result.get_channel(0)["url"] == "https://www.youtube.com/channel/UC123"


def test_channel_tab_result_handles_missing_tab(monkeypatch):
    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return None

    monkeypatch.setattr("youtube_browser.search_handler.utils.YoutubeDL", FakeYDL)

    result = ChannelTabResult(
        "https://www.youtube.com/channel/UC123/streams", "live", "Test Channel"
    )

    assert result.count == 0
    assert result.has_more is False
    assert result.get_display_titles() == []
