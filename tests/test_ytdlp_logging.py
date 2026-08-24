from unittest.mock import MagicMock, patch

import pytest

import utils
from download_handler.downloader import Downloader
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult, _yt_dlp_flat_options


def test_ytdlp_logger_methods():
    mock_logger = MagicMock()
    yt_logger = utils.YtDlpLogger(mock_logger)

    yt_logger.debug("test debug message")
    mock_logger.info.assert_called_with("test debug message")

    yt_logger.info("test info message")
    mock_logger.info.assert_called_with("test info message")

    yt_logger.warning("test warning message")
    mock_logger.warning.assert_called_with("test warning message")

    yt_logger.error("test error message")
    mock_logger.error.assert_called_with("test error message")


def test_player_opts_has_verbose_and_logger():
    assert utils.PLAYER_OPTS.get("verbose") is True
    assert utils.PLAYER_OPTS.get("quiet") is False
    assert utils.PLAYER_OPTS.get("no_warnings") is False
    assert isinstance(utils.PLAYER_OPTS.get("logger"), utils.YtDlpLogger)


def test_get_ydl_instance_includes_verbose_and_logger():
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

    with patch.object(utils, "YoutubeDL", FakeYDL):
        instance = utils.get_ydl_instance(["android", "web"])
        assert instance.opts.get("verbose") is True
        assert instance.opts.get("quiet") is False
        assert isinstance(instance.opts.get("logger"), utils.YtDlpLogger)


def test_yt_dlp_flat_options_has_verbose_and_logger():
    opts = _yt_dlp_flat_options(1, 10)
    assert opts.get("verbose") is True
    assert opts.get("quiet") is False
    assert opts.get("no_warnings") is False
    assert isinstance(opts.get("logger"), utils.YtDlpLogger)


def test_downloader_base_options_has_verbose_and_logger():
    downloader = Downloader(
        "https://youtube.com/watch?v=123", "out", "best", None, None
    )
    opts = downloader._base_options()
    assert opts.get("verbose") is True
    assert opts.get("quiet") is False
    assert opts.get("no_warnings") is False
    assert isinstance(opts.get("logger"), utils.YtDlpLogger)


@pytest.mark.asyncio
async def test_scraper_extracts_stream_without_skipping(monkeypatch):
    data_list = [
        {
            "type": "video",
            "id": "test_id_1",
            "url": "https://www.youtube.com/watch?v=test_id_1",
        }
    ]
    results = SimpleResult(data_list)

    extracted = []

    def fake_get_playable_stream(url, audio_mode):
        extracted.append((url, audio_mode))
        return "https://stream.url/audio.m4a"

    monkeypatch.setattr(utils, "get_playable_stream", fake_get_playable_stream)

    scraper = Scraper(num_workers=1)
    await scraper._set_results(results)
    await scraper._add_item(0, priority=0)

    import asyncio

    task = asyncio.create_task(scraper._worker())
    await asyncio.wait_for(scraper.queue.join(), timeout=5.0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(extracted) > 0
    assert extracted[0][0] == "https://www.youtube.com/watch?v=test_id_1"
