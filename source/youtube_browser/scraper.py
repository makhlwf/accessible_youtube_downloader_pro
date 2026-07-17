import asyncio
import logging
from async_utils import submit_async
import utils

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, num_workers=4):
        self.num_workers = num_workers
        self.queue = asyncio.PriorityQueue()
        self.results = None
        self.audio_mode = True
        self.queued_indices = set()
        self.processing_indices = set()
        self.lock = asyncio.Lock()
        self.workers = []
        self.is_throttled = False
        self._start_future = None

    def _submit(self, coro):
        try:
            return submit_async(coro)
        except RuntimeError as e:
            logger.debug("Could not schedule scraper task: %s", e)
            coro.close()
            return None

    def _ensure_started(self):
        if self._start_future is None or (
            self._start_future.done() and self._start_future.exception() is not None
        ):
            self._start_future = self._submit(self._start_workers())

    async def _start_workers(self):
        self.workers = [task for task in self.workers if not task.done()]
        for _ in range(max(0, self.num_workers - len(self.workers))):
            task = asyncio.create_task(self._worker())
            self.workers.append(task)

    def set_results(self, results):
        self._ensure_started()
        self._submit(self._set_results(results))

    async def _set_results(self, results):
        async with self.lock:
            self.results = results
            self.queued_indices.clear()
            self.processing_indices.clear()
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except asyncio.QueueEmpty:
                    break

    def add_item(self, index, priority=10):
        self._ensure_started()
        self._submit(self._add_item(index, priority))

    async def _add_item(self, index, priority=10):
        async with self.lock:
            if self.results is None:
                return
            if index < 0 or index >= self.results.count:
                return

            # If it's already scraped, don't queue
            if all(
                self.results.get_stream(index, audio_mode=mode) is not None
                for mode in self._prefetch_modes()
            ):
                return

            # If it's high priority (0), we always allow re-queueing to jump the line
            if priority > 0 and index in self.queued_indices:
                return

            if priority == 0:
                self.is_throttled = True
                asyncio.create_task(self._reset_throttle())

            await self.queue.put((priority, index))
            self.queued_indices.add(index)

    def _prefetch_modes(self):
        modes = [self.audio_mode]
        other_mode = not self.audio_mode
        if other_mode not in modes:
            modes.append(other_mode)
        return modes

    async def _reset_throttle(self):
        await asyncio.sleep(2)
        self.is_throttled = False

    async def _worker(self):
        while True:
            try:
                priority, index = await self.queue.get()

                # Aggressive pre-fetching: if a high priority item (like selection) is handled,
                # we don't sleep. If it's the first few items in a search, we also give them a boost.
                if priority > 0 and self.is_throttled:
                    await asyncio.sleep(0.3)  # Reduced sleep

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
                                    and any(
                                        results.get_stream(index, audio_mode=mode)
                                        is None
                                        for mode in self._prefetch_modes()
                                    )
                                ):
                                    if not utils.YoutubeDL:
                                        continue
                                    url = results.get_url(index)
                                    for audio_mode in self._prefetch_modes():
                                        if results.get_stream(
                                            index, audio_mode=audio_mode
                                        ):
                                            continue
                                        stream = await (
                                            asyncio.get_running_loop().run_in_executor(
                                                None,
                                                utils.get_playable_stream,
                                                url,
                                                audio_mode,
                                            )
                                        )
                                        if stream and results == self.results:
                                            results.set_stream(
                                                index,
                                                stream,
                                                audio_mode=audio_mode,
                                            )
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
