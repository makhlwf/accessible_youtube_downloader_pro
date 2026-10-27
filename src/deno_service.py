import atexit
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time

import paths

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


class DenoService:
    def __init__(self, request_timeout=30.0):
        if not 0 < request_timeout <= threading.TIMEOUT_MAX:
            raise ValueError("request_timeout must be positive and finite")
        self.process = None
        # Keep the sequential JS protocol, but never use this lock in stop().
        self.lock = threading.Lock()
        self.request_id = 0
        self._request_timeout = request_timeout
        self._state_lock = threading.Lock()
        self._io = None
        self._generation = 0

    def _discard_process(self, io):
        with self._state_lock:
            if self._io is io:
                self._io = None
                self.process = None
        io.stop()

    def _ensure_process(self, generation=None):
        """Get a live process; send_command serializes calls to this method."""
        with self._state_lock:
            if generation is None:
                generation = self._generation
            if generation != self._generation:
                return None
            old_io = self._io
            if (
                old_io is not None
                and not old_io.stopped.is_set()
                and old_io.process.poll() is None
            ):
                return old_io
            self._io = None
            self.process = None
        if old_io is not None:
            old_io.stop()

        io = None
        try:
            from settings_handler import config_get

            use_deno = bool(config_get("use_deno_backend"))
            yt_service_bin = paths.get_youtube_service_path()
            if not use_deno and yt_service_bin:
                command = [yt_service_bin]
                runtime_name = "Standalone YouTube service"
            else:
                service_script = paths.get_js_runtime_service_script()
                config_path = paths.get_js_runtime_config_path()
                lock_path = paths.get_js_runtime_lock_path()

                command = [
                    paths.get_deno_path(),
                    "run",
                    "--allow-all",
                    "--config",
                    config_path,
                ]
                if os.path.exists(lock_path):
                    command.extend(["--lock", lock_path])
                command.append(service_script)
                runtime_name = "Deno service"

            env = os.environ.copy()
            env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")

            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0,
                cwd=paths.main_path,
                env=env,
            )
            io = _ProcessIO(process)
            io.start()
            # Starting a process must not hold the lifecycle lock. If stop()
            # raced with startup, retire this child rather than publishing it.
            with self._state_lock:
                if generation == self._generation:
                    self._io = io
                    self.process = process
                    logger.info(f"{runtime_name} started: {command[0]}")
                    return io
            io.stop()
        except Exception as e:
            logger.error(f"Failed to start JS service: {e}")
            if io is not None:
                io.stop()
        return None

    def stop(self):
        with self._state_lock:
            # Invalidate queued requests too: they must not resurrect the
            # service during shutdown. A later, new call may start it again.
            self._generation += 1
            io = self._io
            self._io = None
            self.process = None
        if io is not None:
            io.stop()

    def send_command(self, command, params=None):
        # One deadline covers queueing, writing and waiting for the response.
        deadline = time.monotonic() + self._request_timeout
        with self._state_lock:
            generation = self._generation
        if not self.lock.acquire(timeout=max(0, deadline - time.monotonic())):
            logger.warning("JS service request timed out while queued: %s", command)
            return {"error": "Deno service not available"}

        io = None
        try:
            if time.monotonic() >= deadline:
                raise queue.Empty
            self.request_id += 1
            request_id = self.request_id
            payload = (
                json.dumps(
                    {"id": request_id, "command": command, "params": params or {}}
                )
                + "\n"
            )

            io = self._ensure_process(generation)
            if io is None:
                return {"error": "Deno service not available"}
            if time.monotonic() >= deadline:
                raise queue.Empty
            with self._state_lock:
                if generation != self._generation or self._io is not io:
                    return {"error": "Deno service not available"}
                io.requests.put(payload)

            line = io.responses.get(timeout=max(0, deadline - time.monotonic()))
            with self._state_lock:
                if generation != self._generation:
                    return {"error": "Deno service not available"}
            if isinstance(line, Exception):
                raise line
            if not line:
                logger.warning("Deno service pipe broken; restart on next command")
                self._discard_process(io)
                return {"error": "Deno service not available"}

            response = json.loads(line)
            if not isinstance(response, dict):
                logger.error("JS service response is not a JSON object")
                self._discard_process(io)
                return {"error": "Deno service not available"}
            response_id = response.get("id")
            if type(response_id) is not int or response_id != request_id:
                logger.error(
                    "Request ID mismatch: expected %s, got %s", request_id, response_id
                )
                self._discard_process(io)
                return {"error": "Request ID mismatch"}

            if "error" in response:
                return {"error": response["error"]}
            return response.get("result")
        except queue.Empty:
            logger.warning("JS service request timed out: %s", command)
            if io is not None:
                self._discard_process(io)
            return {"error": "Deno service not available"}
        except Exception as e:
            logger.exception("Error in Deno service send_command")
            if io is not None:
                self._discard_process(io)
            return {"error": str(e)}
        finally:
            # Never replay a failed command: writes may already have succeeded.
            self.lock.release()


deno_service = DenoService()
atexit.register(deno_service.stop)
