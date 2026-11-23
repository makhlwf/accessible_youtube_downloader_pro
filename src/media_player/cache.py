"""Thread-safe expiring cache for media data."""

import threading
import time
from collections import OrderedDict


class InfoCache:
    def __init__(self, default_ttl=300, maxsize=256):
        self.cache = OrderedDict()
        self.default_ttl = default_ttl
        self.maxsize = maxsize
        self.lock = threading.Lock()

    def get(self, url, ttl=None):
        if ttl is None:
            ttl = self.default_ttl
        with self.lock:
            if url in self.cache:
                info, timestamp = self.cache[url]
                if time.time() - timestamp < ttl:
                    self.cache.move_to_end(url)
                    return info
                else:
                    del self.cache[url]
        return None

    def set(self, url, info):
        with self.lock:
            now = time.time()
            if url in self.cache:
                self.cache.move_to_end(url)
            self.cache[url] = (info, now)
            while len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    def clear(self):
        with self.lock:
            self.cache.clear()
