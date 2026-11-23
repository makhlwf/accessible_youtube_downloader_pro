"""Worker threads that own the JavaScript service's process pipes."""

import logging
import queue
import threading

logger = logging.getLogger(__name__)


class _ProcessIO:
    """One serialized pipe worker and stderr reader, bound to one process."""

    def __init__(self, process):
        self.process = process
        self.requests = queue.Queue()
        self.responses = queue.Queue()
        self.stopped = threading.Event()
        self._stop_lock = threading.Lock()
        self.worker = None
        self.stderr_reader = None

    def start(self):
        worker_started = False
        try:
            self.worker = threading.Thread(target=self._exchange, daemon=True)
            self.stderr_reader = threading.Thread(target=self._log_stderr, daemon=True)
            self.worker.start()
            worker_started = True
            self.stderr_reader.start()
        except Exception:
            self.stop()
            if not worker_started:
                self._reap()
                self._close(self.process.stdin, self.process.stdout)
            self._close(self.process.stderr)
            raise

    def stop(self):
        with self._stop_lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            # Wake an idle worker and the active caller before killing the child.
            self.requests.put(None)
            self.responses.put(None)
        try:
            self.process.kill()
        except Exception:
            pass

    @staticmethod
    def _close(*streams):
        for stream in streams:
            try:
                stream.close()
            except Exception:
                pass

    def _reap(self):
        try:
            self.process.wait(timeout=1.0)
        except Exception:
            logger.warning("Could not reap stopped JS service", exc_info=True)

    def _exchange(self):
        proc = self.process
        try:
            while not self.stopped.is_set():
                payload = self.requests.get()
                if payload is None or self.stopped.is_set():
                    break
                # Both writing a full pipe and readline can block. Only this
                # process's worker does pipe I/O, never the waiting caller.
                proc.stdin.write(payload)
                proc.stdin.flush()
                line = proc.stdout.readline()
                self.responses.put(line)
                if not line:
                    break
        except Exception as error:
            self.responses.put(error)
        finally:
            self.stop()
            self._reap()
            # Closing a buffered pipe from another thread can itself deadlock.
            # Each reader owns closing its streams after kill releases its I/O.
            self._close(proc.stdin, proc.stdout)

    def _log_stderr(self):
        proc = self.process
        try:
            for line in proc.stderr:
                if line:
                    clean_line = line.strip()
                    if clean_line.startswith("[YOUTUBEJS]"):
                        logger.debug(f"Deno service stderr: {clean_line}")
                    else:
                        logger.error(f"Deno service stderr: {clean_line}")
        except Exception:
            pass
        finally:
            self._close(proc.stderr)
