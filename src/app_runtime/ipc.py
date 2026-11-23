"""Loopback transport shared by the GUI and browser native messaging hosts."""

import json
import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)
IPC_HOST = "127.0.0.1"
IPC_PORT = 57280
IPC_MAX_MESSAGE_BYTES = 64 * 1024


def send_ipc_message(action, url=""):
    payload = json.dumps({"action": action, "url": url}).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        s.connect((IPC_HOST, IPC_PORT))
        s.sendall(payload)


def start_ipc_server(stopping, on_message):
    """Start the listener and deliver messages to on_message on its worker thread."""

    def listen():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.bind((IPC_HOST, IPC_PORT))
                server.listen()
                server.settimeout(0.5)
                while not stopping.is_set():
                    try:
                        conn, _addr = server.accept()
                    except TimeoutError:
                        continue
                    with conn:
                        try:
                            data = bytearray()
                            deadline = time.monotonic() + 1
                            while len(data) <= IPC_MAX_MESSAGE_BYTES:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    raise TimeoutError
                                conn.settimeout(remaining)
                                chunk = conn.recv(4096)
                                if not chunk:
                                    break
                                data.extend(chunk)
                        except OSError:
                            logger.debug(
                                "Could not read local IPC request", exc_info=True
                            )
                            continue
                    if data and len(data) <= IPC_MAX_MESSAGE_BYTES:
                        on_message(bytes(data))
        except OSError:
            logger.exception("Local IPC listener stopped")

    threading.Thread(target=listen, daemon=True).start()
