import json
import logging
import os
import subprocess
import threading

import paths

logger = logging.getLogger(__name__)


class DenoService:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self.request_id = 0

    def _ensure_process(self):
        if self.process and self.process.poll() is None:
            return

        try:
            service_script = paths.get_js_runtime_service_script()
            config_path = paths.get_js_runtime_config_path()
            lock_path = paths.get_js_runtime_lock_path()

            env = os.environ.copy()
            env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")

            command = [
                paths.deno_path,
                "run",
                "--allow-all",
                "--config",
                config_path,
            ]
            if os.path.exists(lock_path):
                command.extend(["--lock", lock_path])
            command.append(service_script)

            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=paths.main_path,
                env=env,
            )

            # Start a thread to log stderr
            threading.Thread(target=self._log_stderr, daemon=True).start()

            logger.info("Deno service started.")
        except Exception as e:
            logger.error(f"Failed to start Deno service: {e}")
            self.process = None

    def stop(self):
        with self.lock:
            if not self.process:
                return
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

    def _log_stderr(self):
        proc = self.process
        if not proc:
            return
        try:
            for line in proc.stderr:
                if line:
                    logger.error(f"Deno service stderr: {line.strip()}")
        except Exception:
            pass

    def send_command(self, command, params=None):
        with self.lock:
            self.request_id += 1
            request_id = self.request_id

            payload = {"id": request_id, "command": command, "params": params or {}}

            try:
                self._ensure_process()
                if not self.process:
                    return {"error": "Deno service not available"}

                self.process.stdin.write(json.dumps(payload) + "\n")
                self.process.stdin.flush()

                line = self.process.stdout.readline()
                if not line:
                    logger.warning("Deno service pipe broken, attempting restart...")
                    self.process = None
                    self._ensure_process()
                    if not self.process:
                        return {"error": "Deno service crashed and failed to restart"}

                    self.process.stdin.write(json.dumps(payload) + "\n")
                    self.process.stdin.flush()
                    line = self.process.stdout.readline()
                    if not line:
                        return {"error": "Deno service failed to respond after restart"}

                response = json.loads(line)
                if response.get("id") != request_id:
                    logger.error(
                        f"Request ID mismatch: expected {request_id}, got {response.get('id')}"
                    )
                    # Force restart on next call if out of sync
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                    self.process = None
                    return {"error": "Request ID mismatch"}

                if "error" in response:
                    return {"error": response["error"]}

                return response.get("result")
            except Exception as e:
                logger.exception(f"Error in Deno service send_command: {e}")
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None
                return {"error": str(e)}


deno_service = DenoService()
