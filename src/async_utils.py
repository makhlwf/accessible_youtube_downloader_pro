import asyncio
import threading

# Global asyncio event loop and thread
_async_loop = None
_async_thread = None
_async_loop_ready = threading.Event()
_async_loop_lock = threading.Lock()
_stopping = False


def start_async_loop():
    global _async_loop, _async_thread, _stopping
    with _async_loop_lock:
        if _async_loop is not None:
            return
        loop = asyncio.new_event_loop()
        _async_loop = loop
        _async_thread = threading.current_thread()
        _stopping = False
        _async_loop_ready.clear()

    asyncio.set_event_loop(loop)

    def mark_ready():
        # Publishing readiness before run_forever caused intermittent failures
        # for the first task submitted during startup.
        with _async_loop_lock:
            if not _stopping:
                _async_loop_ready.set()

    loop.call_soon(mark_ready)
    try:
        loop.run_forever()
    finally:
        try:
            loop.run_until_complete(_cancel_pending_tasks())
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
            with _async_loop_lock:
                _async_loop_ready.clear()
                _async_loop = None
                _async_thread = None


def stop_async_loop():
    global _stopping
    with _async_loop_lock:
        loop = _async_loop
        if loop is None or _stopping:
            return
        _stopping = True
        _async_loop_ready.clear()
        on_loop_thread = threading.current_thread() is _async_thread

    if on_loop_thread:
        # Never block this loop waiting for a future that needs the same loop.
        loop.stop()
        return
    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_cancel_pending_tasks(), loop)
        try:
            future.result(timeout=2)
        except Exception:
            pass
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        pass  # The loop may already have finished shutting down.


def get_async_loop(timeout=5):
    if _async_loop_ready.wait(timeout):
        with _async_loop_lock:
            if _async_loop and not _stopping and _async_loop.is_running():
                return _async_loop
    raise RuntimeError("Async loop not running or not initialized.")


def submit_async(coro):
    """Schedule without ever waiting on the GUI thread for a missing runtime."""
    try:
        return asyncio.run_coroutine_threadsafe(coro, get_async_loop(timeout=0))
    except Exception:
        coro.close()
        raise


def run_in_async_loop(coro):
    """Synchronous bridge for worker threads, not GUI or asyncio callbacks."""
    try:
        loop = get_async_loop()
        if threading.current_thread() is _async_thread:
            raise RuntimeError("Cannot synchronously wait on the async loop thread.")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        coro.close()
        raise
    return future.result()


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
