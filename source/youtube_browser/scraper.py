import asyncio
import logging
import wx
from utils import get_playable_stream

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, num_workers=2):
        self.queue = asyncio.PriorityQueue()
        self.results = None
        self.audio_mode = False
        self.queued_indices = set()
        self.processing_indices = set()
        self.lock = asyncio.Lock()
        self.workers = []
        self.is_throttled = False
        self._loop = asyncio.get_event_loop()
        for _ in range(num_workers):
            task = asyncio.create_task(self._worker())
            self.workers.append(task)

    def set_results(self, results):
        self.results = results
        self.queued_indices.clear()
        self.processing_indices.clear()
        # Clear the queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def add_item(self, index, priority=10):
        async with self.lock:
            if self.results is None:
                return
            if index < 0 or index >= self.results.count:
                return

            # If it's already scraped, don't queue
            if self.results.get_stream(index) is not None:
                return

            # If it's high priority (0), we always allow re-queueing to jump the line
            if priority > 0 and index in self.queued_indices:
                return

            if priority == 0:
                self.is_throttled = True
                asyncio.create_task(self._reset_throttle())

            await self.queue.put((priority, index))
            self.queued_indices.add(index)

    async def _reset_throttle(self):
        await asyncio.sleep(2)
        self.is_throttled = False

    async def _worker(self):
        while True:
            try:
                priority, index = await self.queue.get()

                # Throttle mechanism: if a high priority item is being handled,
                # pause low priority tasks briefly to favor the high priority one.
                if priority > 0 and self.is_throttled:
                    await asyncio.sleep(0.5)

                async with self.lock:
                    if index in self.processing_indices:
                        self.queue.task_done()
                        continue
                    self.processing_indices.add(index)

                results = self.results
                try:
                    if results:
                        try:
                            if index < results.count:
                                # Check if still needed
                                if (
                                    results.get_type(index) == "video"
                                    and results.get_stream(index) is None
                                ):
                                    url = results.get_url(index)
                                    # Direct stream scraping
                                    # Since get_playable_stream is synchronous and might block,
                                    # we run it in a thread pool executor.
                                    stream = (
                                        await asyncio.get_event_loop().run_in_executor(
                                            None,
                                            get_playable_stream,
                                            url,
                                            self.audio_mode,
                                        )
                                    )
                                    if stream and results == self.results:
                                        # Use wx.CallAfter to ensure UI thread-safety if needed,
                                        # though set_stream itself might be thread-safe depending on the implementation.
                                        wx.CallAfter(results.set_stream, index, stream)
                        except Exception as e:
                            logger.debug(f"Scraper task failed for index {index}: {e}")
                finally:
                    async with self.lock:
                        self.processing_indices.discard(index)
                        if index in self.queued_indices:
                            self.queued_indices.discard(index)
                    self.queue.task_done()
            except Exception as e:
                logger.error(f"Scraper worker error: {e}")
                await asyncio.sleep(1)
