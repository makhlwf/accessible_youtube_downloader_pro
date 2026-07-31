import asyncio
import threading

# Global asyncio event loop and thread
_async_loop = None
_async_thread = None
_async_loop_ready = threading.Event()


def start_async_loop():
    global _async_loop
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    _async_loop_ready.set()
    _async_loop.run_forever()


def stop_async_loop():
    if _async_loop and _async_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_cancel_pending_tasks(), _async_loop)
        try:
            future.result(timeout=2)
        except Exception:
            pass
        _async_loop.call_soon_threadsafe(_async_loop.stop)
        _async_loop_ready.clear()


def get_async_loop(timeout=5):
    if _async_loop_ready.wait(timeout) and _async_loop and _async_loop.is_running():
        return _async_loop
    raise RuntimeError("Async loop not running or not initialized.")


def submit_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, get_async_loop())


def run_in_async_loop(coro):
    return submit_async(coro).result()


async def _cancel_pending_tasks():
    current_task = asyncio.current_task()
    tasks = [
        task
        for task in asyncio.all_tasks()
        if task is not current_task and not task.done()
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
