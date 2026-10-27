from unittest.mock import AsyncMock, patch

import pytest

from youtube_browser.search_handler import (
    ChannelTabResult,
    PlaylistResult,
    Search,
    SimpleResult,
    fetch_search_suggestions,
    fetch_search_suggestions_async,
)


@pytest.mark.asyncio
async def test_suggestions_use_platform_region(monkeypatch):
    from youtube_browser import search_handler

    monkeypatch.setattr(search_handler.utils, "get_windows_region", lambda: "DE")
    suggestions = AsyncMock(return_value={"result": ["test result"]})
    monkeypatch.setattr(search_handler.Suggestions, "get", suggestions)
    assert await fetch_search_suggestions_async("test", language="de") == [
        "test result"
    ]
    suggestions.assert_awaited_once_with("test", language="de", region="DE")


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


def test_search_uses_windows_region(monkeypatch):
    captured_kwargs = {}

    def fake_videos_search(query, limit=20, language="ar", region="US"):
        captured_kwargs["query"] = query
        captured_kwargs["language"] = language
        captured_kwargs["region"] = region
        mock_inst = AsyncMock()
        mock_inst.next = AsyncMock(return_value={"result": []})
        return mock_inst

    monkeypatch.setattr(
        "youtube_browser.search_handler.VideosSearch", fake_videos_search
    )
    monkeypatch.setattr(
        "youtube_browser.search_handler.utils.get_windows_region", lambda: "EG"
    )
    monkeypatch.setattr("youtube_browser.search_handler.config_get", lambda key: "ar")

    _ = Search("test query")
    assert captured_kwargs["query"] == "test query"
    assert captured_kwargs["language"] == "ar"
    assert captured_kwargs["region"] == "EG"


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


def test_get_home_feed_validation_missing_deno(monkeypatch):
    import utils

    monkeypatch.setattr(utils, "ensure_deno_installed", lambda **kw: False)

    res = utils.get_home_feed()
    assert res["videos"] == []
    assert res["error"] == "لم يتم تثبيت Deno."


def test_get_home_feed_validation_missing_cookies(monkeypatch):
    import utils

    monkeypatch.setattr(utils, "ensure_deno_installed", lambda **kw: True)
    monkeypatch.setattr(utils, "ensure_cookies_configured", lambda **kw: False)

    res = utils.get_home_feed()
    assert res["videos"] == []
    assert res["error"] == "لم يتم ضبط ملف الكوكيز."


def test_get_home_feed_success(monkeypatch):
    import utils

    monkeypatch.setattr(utils, "ensure_deno_installed", lambda **kw: True)
    monkeypatch.setattr(utils, "ensure_cookies_configured", lambda **kw: True)
    monkeypatch.setattr(utils, "config_get", lambda k: "cookies.txt")
    monkeypatch.setattr(utils, "get_windows_region", lambda: "US")
    monkeypatch.setattr(
        utils.deno_service,
        "send_command",
        lambda cmd, params: {"videos": [{"id": "v1"}], "continuation": "cont1"},
    )

    res = utils.get_home_feed()
    assert len(res["videos"]) == 1
    assert res["videos"][0]["id"] == "v1"
    assert res["continuation"] == "cont1"


def test_get_watch_history_falls_back_without_deno(monkeypatch):
    import utils

    class FakeWatchHistory:
        @classmethod
        def get_page(cls, limit, offset):
            return [{"title": "Local Fallback"}]

    deno_calls = []
    cookie_calls = []

    monkeypatch.setattr(
        utils, "ensure_deno_installed", lambda **kw: deno_calls.append(kw) or False
    )
    monkeypatch.setattr(
        utils, "ensure_cookies_configured", lambda **kw: cookie_calls.append(kw) or True
    )
    monkeypatch.setattr(utils, "WatchHistory", FakeWatchHistory)

    res = utils.get_watch_history()
    assert res["videos"][0]["title"] == "Local Fallback"
    assert res["source"] == "local"
    assert len(deno_calls) == 1
    assert deno_calls[0]["feature_name"] == "سجل المشاهدة أونلاين"
    assert len(cookie_calls) == 0
    assert "عذراً، يتطلب عرض سجل يوتيوب أونلاين" in res["error"]


def test_get_watch_history_falls_back_without_cookies(monkeypatch):
    import utils

    class FakeWatchHistory:
        @classmethod
        def get_page(cls, limit, offset):
            return [{"title": "Local Fallback"}]

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
    monkeypatch.setattr(utils, "WatchHistory", FakeWatchHistory)

    res = utils.get_watch_history()
    assert res["videos"][0]["title"] == "Local Fallback"
    assert res["source"] == "local"
    assert len(deno_calls) == 1
    assert len(cookie_calls) == 1
    assert cookie_calls[0]["feature_name"] == "سجل المشاهدة أونلاين"
    assert "عذراً، يتطلب عرض سجل يوتيوب أونلاين" in res["error"]


def test_local_watch_history_response_handles_invalid_continuation(monkeypatch):
    import utils

    class FakeWatchHistory:
        @classmethod
        def get_page(cls, limit, offset):
            assert offset == 0
            return []

    monkeypatch.setattr(utils, "WatchHistory", FakeWatchHistory)
    res = utils._local_watch_history_response(continuation="not_an_int")
    assert res["source"] == "local"
    assert res["videos"] == []


@pytest.mark.asyncio
async def test_fetch_search_suggestions_async_success():
    with patch(
        "youtube_browser.search_handler.Suggestions.get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {"result": ["python tutorial", "python for beginners"]}
        res = await fetch_search_suggestions_async("python", language="en", region="US")
        assert res == ["python tutorial", "python for beginners"]
        mock_get.assert_awaited_once_with("python", language="en", region="US")


@pytest.mark.asyncio
async def test_fetch_search_suggestions_async_empty_query():
    res = await fetch_search_suggestions_async("   ")
    assert res == []


@pytest.mark.asyncio
async def test_fetch_search_suggestions_async_error_handling():
    with patch(
        "youtube_browser.search_handler.Suggestions.get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.side_effect = RuntimeError("Network error")
        res = await fetch_search_suggestions_async("python")
        assert res == []


def test_fetch_search_suggestions_sync():
    with patch(
        "youtube_browser.search_handler.Suggestions.get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {"result": ["python basics"]}
        res = fetch_search_suggestions("python", language="en", region="US")
        assert res == ["python basics"]


def test_search_initialization_normalizes_language_and_region():
    with (
        patch("youtube_browser.search_handler.config_get", return_value="English"),
        patch(
            "youtube_browser.search_handler.utils.get_windows_region",
            return_value=None,
        ),
        patch("youtube_browser.search_handler.VideosSearch") as mock_videos_search,
    ):
        Search("test query", filter=0)
        mock_videos_search.assert_called_once_with(
            "test query", limit=20, language="en", region="US"
        )


@pytest.mark.asyncio
async def test_fetch_search_suggestions_normalizes_unrecognized_language():
    with patch(
        "youtube_browser.search_handler.Suggestions.get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {"result": ["suggestion 1"]}
        res = await fetch_search_suggestions_async(
            "test", language="English", region="invalid_region"
        )
        assert res == ["suggestion 1"]
        mock_get.assert_awaited_once_with("test", language="en", region="US")


@pytest.mark.asyncio
async def test_search_filters_livestream():
    from youtube_browser.search_handler import (
        SEARCH_FILTER_LIVE,
        Search,
        SearchMode,
    )

    fake_result = {
        "result": [
            {
                "type": "video",
                "id": "live123",
                "title": "Live News Stream",
                "link": "https://www.youtube.com/watch?v=live123",
                "duration": None,
                "publishedTime": None,
                "viewCount": {"short": None, "text": None},
                "channel": {
                    "name": "News Channel",
                    "link": "https://www.youtube.com/channel/c123",
                },
            }
        ]
    }

    with (
        patch("youtube_browser.search_handler.config_get", return_value="ar"),
        patch(
            "youtube_browser.search_handler.utils.get_windows_region", return_value="US"
        ),
        patch("youtube_browser.search_handler.CustomSearch") as MockCustomSearch,
    ):
        mock_instance = MockCustomSearch.return_value
        mock_instance.next = AsyncMock(return_value=fake_result)
        mock_instance.continuationKey = "cont_live"

        search = Search("news", filter=SEARCH_FILTER_LIVE)
        MockCustomSearch.assert_called_once_with(
            "news", SearchMode.livestreams, limit=20, language="ar", region="US"
        )
        assert mock_instance.searchMode == (True, False, False)

        await search.init_async()
        assert search.count == 1
        assert search.get_title(0) == "Live News Stream"
        assert search.get_url(0) == "https://www.youtube.com/watch?v=live123"
        assert search.get_type(0) == "video"
        assert search.get_views(0) is None
        titles = search.get_titles()
        assert len(titles) == 1
        assert "None" not in titles[0]
        assert "Live News Stream" in titles[0]


@pytest.mark.asyncio
async def test_search_filters_upload_date():
    from youtube_browser.search_handler import (
        SEARCH_FILTER_UPLOAD_DATE,
        Search,
        VideoSortOrder,
    )

    fake_result = {
        "result": [
            {
                "type": "video",
                "id": "new123",
                "title": "Recent Video",
                "link": "https://www.youtube.com/watch?v=new123",
                "duration": "10:30",
                "publishedTime": "2 hours ago",
                "viewCount": {"short": "500 views"},
                "channel": {
                    "name": "Creator",
                    "link": "https://www.youtube.com/channel/cCreator",
                },
            }
        ]
    }

    with (
        patch("youtube_browser.search_handler.config_get", return_value="ar"),
        patch(
            "youtube_browser.search_handler.utils.get_windows_region", return_value="US"
        ),
        patch("youtube_browser.search_handler.CustomSearch") as MockCustomSearch,
    ):
        mock_instance = MockCustomSearch.return_value
        mock_instance.next = AsyncMock(return_value=fake_result)

        search = Search("minecraft", filter=SEARCH_FILTER_UPLOAD_DATE)
        MockCustomSearch.assert_called_once_with(
            "minecraft", VideoSortOrder.uploadDate, limit=20, language="ar", region="US"
        )
        assert mock_instance.searchMode == (True, False, False)

        await search.init_async()
        assert search.count == 1
        assert search.get_title(0) == "Recent Video"
        titles = search.get_titles()
        assert "2 hours ago" in titles[0]
        assert "None" not in titles[0]


@pytest.mark.asyncio
async def test_search_filters_view_count():
    from youtube_browser.search_handler import (
        SEARCH_FILTER_VIEW_COUNT,
        Search,
        VideoSortOrder,
    )

    fake_result = {
        "result": [
            {
                "type": "video",
                "id": "top123",
                "title": "Viral Video",
                "link": "https://www.youtube.com/watch?v=top123",
                "duration": "05:00",
                "publishedTime": "1 year ago",
                "viewCount": {"short": "50M views"},
                "channel": {
                    "name": "Famous Channel",
                    "link": "https://www.youtube.com/channel/cFamous",
                },
            }
        ]
    }

    with (
        patch("youtube_browser.search_handler.config_get", return_value="ar"),
        patch(
            "youtube_browser.search_handler.utils.get_windows_region", return_value="US"
        ),
        patch("youtube_browser.search_handler.CustomSearch") as MockCustomSearch,
    ):
        mock_instance = MockCustomSearch.return_value
        mock_instance.next = AsyncMock(return_value=fake_result)

        search = Search("python tutorial", filter=SEARCH_FILTER_VIEW_COUNT)
        MockCustomSearch.assert_called_once_with(
            "python tutorial",
            VideoSortOrder.viewCount,
            limit=20,
            language="ar",
            region="US",
        )
        assert mock_instance.searchMode == (True, False, False)

        await search.init_async()
        assert search.count == 1
        assert search.get_title(0) == "Viral Video"
        assert search.get_views(0) == "50M views"
        titles = search.get_titles()
        assert "50M views" in titles[0]


def test_search_filter_normalization():
    from youtube_browser.search_handler import (
        SEARCH_FILTER_ALL,
        SEARCH_FILTER_CHANNEL,
        SEARCH_FILTER_LIVE,
        SEARCH_FILTER_PLAYLIST,
        SEARCH_FILTER_UPLOAD_DATE,
        SEARCH_FILTER_VIEW_COUNT,
        Search,
    )

    assert Search.normalize_filter(0) == SEARCH_FILTER_ALL
    assert Search.normalize_filter(1) == SEARCH_FILTER_LIVE
    assert Search.normalize_filter(2) == SEARCH_FILTER_UPLOAD_DATE
    assert Search.normalize_filter(3) == SEARCH_FILTER_VIEW_COUNT
    assert Search.normalize_filter(4) == SEARCH_FILTER_PLAYLIST
    assert Search.normalize_filter(5) == SEARCH_FILTER_CHANNEL

    assert Search.normalize_filter("live") == SEARCH_FILTER_LIVE
    assert Search.normalize_filter("livestream") == SEARCH_FILTER_LIVE
    assert Search.normalize_filter("date") == SEARCH_FILTER_UPLOAD_DATE
    assert Search.normalize_filter("upload_date") == SEARCH_FILTER_UPLOAD_DATE
    assert Search.normalize_filter("views") == SEARCH_FILTER_VIEW_COUNT
    assert Search.normalize_filter("view_count") == SEARCH_FILTER_VIEW_COUNT
    assert Search.normalize_filter("playlist") == SEARCH_FILTER_PLAYLIST
    assert Search.normalize_filter("channel") == SEARCH_FILTER_CHANNEL
    assert Search.normalize_filter("1") == SEARCH_FILTER_LIVE
    assert Search.normalize_filter("unknown") == SEARCH_FILTER_ALL


@pytest.mark.asyncio
async def test_search_custom_filter_polymorphic_parsing():
    from youtube_browser.search_handler import SEARCH_FILTER_VIEW_COUNT, Search

    fake_result = {
        "result": [
            {
                "type": "playlist",
                "id": "pl1",
                "title": "Top Playlist",
                "link": "https://www.youtube.com/playlist?list=pl1",
                "videoCount": "42 videos",
                "channel": {"name": "Mix Channel", "link": ""},
            },
            {
                "type": "channel",
                "id": "ch1",
                "title": "Top Channel",
                "link": "https://www.youtube.com/channel/ch1",
                "videoCount": "100",
                "subscribers": "10M",
            },
            {
                "type": "video",
                "id": "v1",
                "title": "Top Video",
                "link": "https://www.youtube.com/watch?v=v1",
                "duration": "02:00",
                "publishedTime": "1 day ago",
                "viewCount": {"short": "1M views"},
                "channel": {"name": "Video Creator", "link": ""},
            },
        ]
    }

    with patch("youtube_browser.search_handler.CustomSearch") as MockCustomSearch:
        mock_instance = MockCustomSearch.return_value
        mock_instance.next = AsyncMock(return_value=fake_result)

        search = Search("popular", filter=SEARCH_FILTER_VIEW_COUNT)
        await search.init_async()

        assert search.count == 3
        assert search.get_type(0) == "playlist"
        assert search.get_type(1) == "channel"
        assert search.get_type(2) == "video"


def test_cli_cmd_search_filters():
    from unittest.mock import MagicMock

    from cli.commands import cmd_search

    args = MagicMock()
    args.query = "python"
    args.pages = 1
    emitter = MagicMock()

    for type_name, expected_filter in [
        ("video", 0),
        ("live", 1),
        ("upload_date", 2),
        ("view_count", 3),
        ("playlist", 4),
        ("channel", 5),
    ]:
        args.type = type_name
        with (
            patch("cli.commands.Search") as MockSearch,
            patch("cli.commands.run_async"),
        ):
            mock_inst = MockSearch.return_value
            mock_inst.count = 1
            mock_inst.get_display_titles.return_value = ["Item 1"]
            mock_inst.get_items.return_value = [{"title": "Item 1"}]

            res = cmd_search(args, emitter)
            assert res == 0
            MockSearch.assert_called_once_with("python", filter=expected_filter)


@pytest.mark.asyncio
async def test_suggestion_timeout_cancels_stalled_request(monkeypatch):
    import asyncio

    from youtube_browser import search_handler

    cancelled = False

    async def stalled(*args, **kwargs):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(search_handler.Suggestions, "get", stalled)
    monkeypatch.setattr(search_handler, "SEARCH_SUGGESTIONS_TIMEOUT_SECONDS", 0.01)
    result = await asyncio.wait_for(
        fetch_search_suggestions_async("query", language="en", region="GB"), timeout=2
    )
    assert result == []
    assert cancelled
