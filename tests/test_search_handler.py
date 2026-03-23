import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from youtube_browser.search_handler import PlaylistResult, SimpleResult, Search

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
                "channel": {"name": "Channel 1", "link": "https://youtube.com/channel/c1"}
            }
        ]
    }

    with patch("youtube_browser.search_handler.Playlist") as MockPlaylist:
        MockPlaylist.getVideos = AsyncMock(return_value=playlist_data)

        res = PlaylistResult(url)
        await res.init_async()

        assert res.title == "Test Playlist"
        assert len(res.videos) == 1
        assert res.videos[0]["title"] == "Video 1"
        assert res.get_url(0) == "https://youtube.com/watch?v=vid1"

def test_simple_result():
    data = [{"url": "url1", "title": "Title 1", "type": "video"}]
    res = SimpleResult(data)
    assert len(res) == 1
    assert res.get_url(0) == "url1"
    assert res.get_title(0) == "Title 1"
    assert res.get_type(0) == "video"

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
                "channel": {"name": "Channel 1", "link": "https://youtube.com/channel/c1"}
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
