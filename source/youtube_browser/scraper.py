import queue
import threading
import logging
from utils import get_playable_stream

logger = logging.getLogger(__name__)

class Scraper:
    def __init__(self, num_workers=5):
        self.queue = queue.PriorityQueue()
        self.results = None
        self.queued_indices = set()
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
                results = self.results
                if results and index < results.count:
                    # Check if still needed
                    if results.get_type(index) == "video" and results.get_stream(index) is None:
                        url = results.get_url(index)
                        try:
                            # Direct stream scraping
                            stream = get_playable_stream(url)
                            if stream and results == self.results:
                                results.set_stream(index, stream)
                        except Exception as e:
                            logger.debug(f"Scraper failed for {url}: {e}")

                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Scraper worker error: {e}")
