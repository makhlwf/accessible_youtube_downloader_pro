import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from youtube_browser import scraper as scraper_module
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult


def make_results(*urls):
    return SimpleResult([{"type": "video", "url": url} for url in urls])


@pytest_asyncio.fixture
async def scraper(monkeypatch):
    monkeypatch.setattr(scraper_module.utils, "YoutubeDL", object())
    instance = Scraper(num_workers=2)
    yield instance
    await instance._close()


@pytest.mark.asyncio
async def test_repeated_selection_is_deduplicated_and_priority_promoted(
    scraper, monkeypatch
):
    extract = AsyncMock(return_value="stream")
    monkeypatch.setattr(scraper_module.asyncio, "to_thread", extract)
    results = make_results("first", "selected")
    await scraper._set_results(results)
    await scraper._add_item(0)
    await scraper._add_item(1)
    for _ in range(1000):
        await scraper._add_item(1, priority=0)
    # Two items plus one superseded priority entry, not 1,002 jobs.
    assert scraper.queue.qsize() == 3
    await scraper._start_workers()
    await asyncio.wait_for(scraper.queue.join(), timeout=2)
    assert extract.await_count == 4  # exactly two modes per video
    assert extract.await_args_list[0].args[1] == "selected"
    assert not scraper.queued_indices
    assert not scraper.processing_indices


@pytest.mark.asyncio
async def test_old_completion_cannot_clear_new_inflight_item(scraper, monkeypatch):
    old_started = asyncio.Event()
    new_started = asyncio.Event()
    release_old = asyncio.Event()
    release_new = asyncio.Event()
    old_finished = asyncio.Event()
    calls = []

    async def extract(function, url, audio_mode):
        calls.append((url, audio_mode))
        if url == "old":
            old_started.set()
            await release_old.wait()
            old_finished.set()
        else:
            new_started.set()
            await release_new.wait()
        return f"{url}-{audio_mode}"

    monkeypatch.setattr(scraper_module.asyncio, "to_thread", extract)
    old = make_results("old")
    new = make_results("new")
    await scraper._set_results(old)
    await scraper._add_item(0)
    await scraper._start_workers()
    await asyncio.wait_for(old_started.wait(), timeout=2)
    await scraper._set_results(new)
    await scraper._add_item(0)
    await asyncio.wait_for(new_started.wait(), timeout=2)
    release_old.set()
    await asyncio.wait_for(old_finished.wait(), timeout=2)
    assert scraper.processing_indices == {0}
    for _ in range(100):
        await scraper._add_item(0, priority=0)
    assert scraper.queue.empty()
    release_new.set()
    await asyncio.wait_for(scraper.queue.join(), timeout=2)
    assert calls == [("old", True), ("new", True), ("new", False)]
    assert old.get_stream(0, True) is None
    assert new.get_stream(0, True) == "new-True"
    assert new.get_stream(0, False) == "new-False"


@pytest.mark.asyncio
async def test_same_results_do_not_reset_pending_prefetch(scraper):
    results = make_results("one")
    await scraper._set_results(results)
    await scraper._add_item(0)
    generation = scraper._generation
    await scraper._set_results(results)
    assert scraper._generation == generation
    assert scraper.queued_indices == {0}
    assert scraper.queue.qsize() == 1


@pytest.mark.asyncio
async def test_close_cancels_workers_and_discards_queued_work(scraper, monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def extract(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(scraper_module.asyncio, "to_thread", extract)
    await scraper._set_results(make_results("one", "two", "three"))
    for index in range(3):
        await scraper._add_item(index)
    await scraper._start_workers()
    await asyncio.wait_for(started.wait(), timeout=2)
    workers = list(scraper.workers)
    await scraper._close()
    await asyncio.wait_for(scraper.queue.join(), timeout=2)
    assert cancelled.is_set()
    assert all(task.done() for task in workers)
    assert scraper.workers == []
    assert scraper.results is None
    await scraper._add_item(0)
    assert scraper.queue.empty()
    submit = Mock()
    monkeypatch.setattr(scraper_module, "submit_async", submit)
    scraper.add_item(0)
    scraper.set_results(make_results("four"))
    scraper.close()
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_extraction_does_not_stop_workers(scraper, monkeypatch):
    extract = AsyncMock(side_effect=[RuntimeError("offline"), "audio", "video"])
    monkeypatch.setattr(scraper_module.asyncio, "to_thread", extract)
    results = make_results("bad", "good")
    await scraper._set_results(results)
    await scraper._add_item(0)
    await scraper._add_item(1)
    await scraper._start_workers()
    await asyncio.wait_for(scraper.queue.join(), timeout=2)
    assert results.get_stream(1, True) == "audio"
    assert results.get_stream(1, False) == "video"
    assert all(not worker.done() for worker in scraper.workers)


@pytest.mark.asyncio
async def test_nonvideo_and_cached_items_are_not_queued(scraper):
    results = SimpleResult(
        [
            {"type": "playlist", "url": "playlist"},
            {
                "type": "video",
                "url": "cached",
                "audio_stream": "a",
                "video_stream": "v",
            },
        ]
    )
    await scraper._set_results(results)
    for index in (-1, 0, 1, 2):
        await scraper._add_item(index, priority=0)
    assert scraper.queue.empty()


def test_prefetch_closes_only_when_owning_window_is_destroyed():
    owner = Mock()
    scraper = Scraper(owner=owner)
    scraper.close = Mock()
    handler = owner.Bind.call_args.args[1]
    child_event = Mock()
    child_event.GetEventObject.return_value = Mock()
    handler(child_event)
    scraper.close.assert_not_called()
    child_event.Skip.assert_called_once()
    owner_event = Mock()
    owner_event.GetEventObject.return_value = owner
    handler(owner_event)
    scraper.close.assert_called_once()
    owner_event.Skip.assert_called_once()


def test_cancelled_worker_start_can_be_retried(monkeypatch):
    from concurrent.futures import Future

    scraper = Scraper()
    scraper._start_future = Future()
    scraper._start_future.cancel()
    submitted = []

    def submit(coro):
        submitted.append(coro)
        coro.close()
        return Future()

    monkeypatch.setattr(scraper, "_submit", submit)
    scraper._ensure_started()
    assert len(submitted) == 1
