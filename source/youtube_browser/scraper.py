import queue
import threading
import logging
from utils import get_playable_stream

logger = logging.getLogger(__name__)

class Scraper:
    def __init__(self, num_workers=10):
        self.queue = queue.PriorityQueue()
        self.results = None
        self.audio_mode = False
        self.queued_indices = set()
        self.processing_indices = set()
        self.lock = threading.Lock()
        self.workers = []
        for _ in range(num_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)

    def set_results(self, results):
        with self.lock:
            self.results = results
            self.queued_indices.clear()
            self.processing_indices.clear()
            # Clear the queue
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except queue.Empty:
                    break

    def add_item(self, index, priority=10):
        with self.lock:
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

            self.queue.put((priority, index))
            self.queued_indices.add(index)

    def _worker(self):
        while True:
            try:
                priority, index = self.queue.get(timeout=1)
                with self.lock:
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
                                    stream = get_playable_stream(url, audio_mode=self.audio_mode)
                                    if stream and results == self.results:
                                        results.set_stream(index, stream)
                        except Exception as e:
                            logger.debug(f"Scraper task failed for index {index}: {e}")
                finally:
                    with self.lock:
                        self.processing_indices.discard(index)
                        if index in self.queued_indices:
                            self.queued_indices.discard(index)
                    self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Scraper worker error: {e}")
