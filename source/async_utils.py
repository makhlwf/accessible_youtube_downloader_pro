import asyncio
import threading

# Global asyncio event loop and thread
_async_loop = None
_async_thread = None


def start_async_loop():
    global _async_loop
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    _async_loop.run_forever()


def stop_async_loop():
    global _async_loop
    if _async_loop and _async_loop.is_running():
        _async_loop.call_soon_threadsafe(_async_loop.stop)


def run_in_async_loop(coro):
    global _async_loop
    if _async_loop and _async_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
        # You might want to add error handling or a timeout here
        return future.result()
    raise RuntimeError("Async loop not running or not initialized.")
