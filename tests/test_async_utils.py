import asyncio
import inspect
import threading
from unittest.mock import Mock

import pytest

import async_utils


@pytest.fixture
def running_loop():
    thread = threading.Thread(target=async_utils.start_async_loop, daemon=True)
    thread.start()
    loop = async_utils.get_async_loop(timeout=2)
    yield loop
    async_utils.stop_async_loop()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert loop.is_closed()


def test_submit_fails_without_waiting_and_closes_coroutine(monkeypatch):
    getter = Mock(side_effect=RuntimeError("not ready"))
    monkeypatch.setattr(async_utils, "get_async_loop", getter)
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="not ready"):
        async_utils.submit_async(coro)
    getter.assert_called_once_with(timeout=0)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED


def test_loop_is_running_when_ready_and_accepts_first_submission(running_loop):
    assert running_loop.is_running()
    result = async_utils.submit_async(asyncio.sleep(0, result="ready"))
    assert result.result(timeout=2) == "ready"


def test_duplicate_start_does_not_replace_running_loop(running_loop):
    duplicate = threading.Thread(target=async_utils.start_async_loop, daemon=True)
    duplicate.start()
    duplicate.join(timeout=2)
    assert not duplicate.is_alive()
    assert async_utils.get_async_loop(timeout=0) is running_loop


def test_synchronous_bridge_rejects_loop_thread_deadlock(running_loop):
    async def call_bridge():
        coro = asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="synchronously wait"):
            async_utils.run_in_async_loop(coro)
        assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED
        return "safe"

    assert async_utils.submit_async(call_bridge()).result(timeout=2) == "safe"


def test_stop_cancels_tasks_and_clears_readiness(running_loop):
    started = threading.Event()
    cancelled = threading.Event()

    async def pending():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    future = async_utils.submit_async(pending())
    assert started.wait(timeout=2)
    async_utils.stop_async_loop()
    assert cancelled.wait(timeout=2)
    assert future.cancelled()
    with pytest.raises(RuntimeError):
        async_utils.get_async_loop(timeout=0)


def test_worker_bridge_failure_closes_coroutine(monkeypatch):
    monkeypatch.setattr(
        async_utils, "get_async_loop", Mock(side_effect=RuntimeError("stopped"))
    )
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="stopped"):
        async_utils.run_in_async_loop(coro)
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED
