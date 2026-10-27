import asyncio
import logging

import utils
from async_utils import submit_async

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, num_workers=4, *, owner=None):
        self.num_workers = num_workers
        self.queue = asyncio.PriorityQueue()
        self.results = None
        self.audio_mode = True
        self.queued_indices = set()
        self.processing_indices = set()
        self.lock = asyncio.Lock()
        self.workers = []
        self._queued_priorities = {}
        self._generation = 0
        self._closed = False
        self._start_future = None
        if owner is not None:
            # Bind on the GUI thread. Ignore child-destroy events that bubble up.
            import wx

            def on_destroy(event):
                if event.GetEventObject() is owner:
                    self.close()
                event.Skip()

            owner.Bind(wx.EVT_WINDOW_DESTROY, on_destroy)

    def _submit(self, coro):
        try:
            return submit_async(coro)
        except RuntimeError as e:
            logger.debug("Could not schedule scraper task: %s", e)
            coro.close()
            return None

    def _ensure_started(self):
        if self._closed:
            return
        if self._start_future is None or (
            self._start_future.done()
            and (
                self._start_future.cancelled()
                or self._start_future.exception() is not None
            )
        ):
            self._start_future = self._submit(self._start_workers())

    async def _start_workers(self):
        if self._closed:
            return
        self.workers = [task for task in self.workers if not task.done()]
        for _ in range(max(0, self.num_workers - len(self.workers))):
            task = asyncio.create_task(self._worker())
            self.workers.append(task)

    def set_results(self, results):
        if self._closed:
            return
        self._ensure_started()
        self._submit(self._set_results(results))

    def _clear_queue(self):
        self.queued_indices.clear()
        self._queued_priorities.clear()
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()

    async def _set_results(self, results):
        async with self.lock:
            if self._closed or results is self.results:
                return
            self._generation += 1
            self.results = results
            self._clear_queue()
            self.processing_indices.clear()

    def add_item(self, index, priority=10):
        if self._closed:
            return
        self._ensure_started()
        self._submit(self._add_item(index, priority))

    async def _add_item(self, index, priority=10):
        async with self.lock:
            if self._closed or self.results is None:
                return
            if index < 0 or index >= self.results.count:
                return
            if self.results.get_type(index) != "video":
                return
            if index in self.processing_indices:
                return
            if all(
                self.results.get_stream(index, audio_mode=mode) is not None
                for mode in self._prefetch_modes()
            ):
                return

            previous_priority = self._queued_priorities.get(index)
            if previous_priority is not None and previous_priority <= priority:
                return

            # One pending request per item, with at most one normal -> urgent
            # promotion. The worker discards superseded queue entries. Holding
            # an arrow key must not enqueue hundreds of duplicate extractions.
            self._queued_priorities[index] = priority
            self.queue.put_nowait((priority, self._generation, index))
            self.queued_indices.add(index)

    def _prefetch_modes(self):
        return [self.audio_mode, not self.audio_mode]

    def close(self):
        """Stop prefetching without waiting for network I/O on the GUI thread."""
        if self._closed:
            return
        self._closed = True
        self._submit(self._close())

    async def _close(self):
        self._closed = True
        self._generation += 1
        self.results = None
        self._clear_queue()
        self.processing_indices.clear()
        workers, self.workers = self.workers, []
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def _worker(self):
        while not self._closed:
            priority, generation, index = await self.queue.get()
            claimed = False
            try:
                async with self.lock:
                    if (
                        self._closed
                        or generation != self._generation
                        or self._queued_priorities.get(index) != priority
                        or index in self.processing_indices
                    ):
                        continue
                    self._queued_priorities.pop(index, None)
                    self.queued_indices.discard(index)
                    self.processing_indices.add(index)
                    claimed = True
                    results = self.results

                if results is None or not utils.YoutubeDL:
                    continue
                url = results.get_url(index)
                for audio_mode in self._prefetch_modes():
                    # A result change can occur while extraction is in flight.
                    # Do not start its second mode or overwrite the new result.
                    if self._closed or generation != self._generation:
                        break
                    if results.get_stream(index, audio_mode=audio_mode) is not None:
                        continue
                    stream = await asyncio.to_thread(
                        utils.get_playable_stream, url, audio_mode
                    )
                    if self._closed or generation != self._generation:
                        break
                    if stream:
                        results.set_stream(index, stream, audio_mode=audio_mode)
            except Exception:
                logger.exception("Scraper task failed for index %s", index)
            finally:
                if claimed and generation == self._generation:
                    self.processing_indices.discard(index)
                self.queue.task_done()
