"""Local Discord IPC connection and frame exchange."""

import json
import logging
import os
import socket
import struct
import sys
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# Discord RPC Limits
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


class DiscordRPCClient:
    """Low-level cross-platform Discord IPC client."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.stream = None
        self._sock = None
        self.last_response: dict[str, Any] | None = None

    def connect(self) -> bool:
        """Attempt to connect to a local Discord IPC pipe or socket."""
        self.close()
        if sys.platform == "win32":
            for i in range(10):
                pipe_path = rf"\\.\pipe\discord-ipc-{i}"
                try:
                    self.stream = open(pipe_path, "r+b", buffering=0)  # noqa: SIM115
                    if self._handshake():
                        return True
                    self.close()
                except OSError:
                    continue
        else:
            if not hasattr(socket, "AF_UNIX"):
                return False
            candidates = []
            env_paths = [
                os.environ.get("XDG_RUNTIME_DIR"),
                f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else None,
                os.environ.get("TMPDIR"),
                os.environ.get("TMP"),
                os.environ.get("TEMP"),
                "/tmp",
            ]
            for base in filter(None, env_paths):
                for i in range(10):
                    candidates.append(os.path.join(base, f"discord-ipc-{i}"))

            for sock_path in candidates:
                if not os.path.exists(sock_path):
                    continue
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect(sock_path)
                    self._sock = s
                    self.stream = s.makefile("rwb", buffering=0)
                    if self._handshake():
                        return True
                    self.close()
                except OSError:
                    self.close()
                    continue

        return False

    def is_connected(self) -> bool:
        return self.stream is not None

    def _read_exact(self, size: int) -> bytes:
        if not self.stream:
            raise EOFError("No open stream")
        data = bytearray()
        while len(data) < size:
            chunk = self.stream.read(size - len(data))
            if not chunk:
                raise EOFError("Stream closed while reading")
            data.extend(chunk)
        return bytes(data)

    def _handshake(self) -> bool:
        try:
            payload = json.dumps({"v": 1, "client_id": self.client_id}).encode("utf-8")
            self.stream.write(struct.pack("<II", OP_HANDSHAKE, len(payload)) + payload)
            header = self._read_exact(8)
            _opcode, length = struct.unpack("<II", header)
            body = self._read_exact(length)
            data = json.loads(body.decode("utf-8"))
            return data.get("cmd") == "DISPATCH" and data.get("evt") == "READY"
        except Exception as e:
            logger.debug("Discord IPC handshake failed: %s", e)
            return False

    def send_activity(self, activity: dict[str, Any] | None) -> bool:
        """Send SET_ACTIVITY payload to Discord.

        The boolean return reflects whether the IPC transaction completed over a
        healthy connection. A Discord-level validation rejection (e.g. a bad
        button URL producing an "Invalid Form Body") is logged as a warning and
        stored in :attr:`last_response`, but does not drop the connection, so it
        can be diagnosed without triggering a reconnect loop.
        """
        if not self.stream:
            return False
        try:
            msg = {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": str(uuid.uuid4()),
            }
            data = json.dumps(msg).encode("utf-8")
            self.stream.write(struct.pack("<II", OP_FRAME, len(data)) + data)
            header = self._read_exact(8)
            _opcode, length = struct.unpack("<II", header)
            body = self._read_exact(length)
            try:
                self.last_response = json.loads(body.decode("utf-8"))
            except ValueError, UnicodeDecodeError:
                self.last_response = None
            if isinstance(self.last_response, dict) and (
                self.last_response.get("evt") == "ERROR"
            ):
                err = self.last_response.get("data") or {}
                logger.warning(
                    "Discord rejected activity (code %s): %s",
                    err.get("code"),
                    err.get("message"),
                )
            return True
        except Exception as e:
            logger.debug("Failed to send Discord activity: %s", e)
            self.close()
            return False

    def close(self):
        """Close connection stream and socket."""
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
