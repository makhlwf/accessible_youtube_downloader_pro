import json
import logging
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid
from typing import Any

import application
from language_handler import _
from settings_handler import config_get

logger = logging.getLogger(__name__)

# HexPlayer Discord Application ID and Public Key
DEFAULT_CLIENT_ID = "1557530351629246495"
PUBLIC_KEY = "364d362a1cf2adeb9c5256e2eb225df5bee00801f4b938d8df751a6583277ae1"
APP_ICON_URL = (
    "https://raw.githubusercontent.com/makhlwf/HexPlayer/master/assets/icon.png"
)

# Discord RPC Limits
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

MAX_TEXT_BYTES = 128
MAX_BUTTON_LABEL_BYTES = 32


def truncate_utf8(text: str | None, max_bytes: int = MAX_TEXT_BYTES) -> str:
    """Safely truncate text to a maximum byte length without splitting UTF-8 characters."""
    if not text:
        return ""
    text_str = str(text).strip()
    encoded = text_str.encode("utf-8")
    if len(encoded) <= max_bytes:
        res = text_str
    else:
        res = encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()
    if len(res) == 1:
        res = res + " "
    return res


def extract_video_id(url: str | None) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if len(url) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"/shorts/([a-zA-Z0-9_-]{11})",
        r"/embed/([a-zA-Z0-9_-]{11})",
        r"/v/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


class DiscordRPCClient:
    """Low-level cross-platform Discord IPC client."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.stream = None
        self._sock = None

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
        """Send SET_ACTIVITY payload to Discord."""
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
            self._read_exact(length)
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


class DiscordPresence:
    """High-level Discord Rich Presence manager with background worker thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._update_event = threading.Event()
        self._current_activity: dict[str, Any] | None = None
        self._pending_activity: dict[str, Any] | None = None
        self._dirty = False
        self._client: DiscordRPCClient | None = None
        self._client_id = DEFAULT_CLIENT_ID
        self._enabled = True
        self._show_details = True
        self._show_buttons = True
        self._session_start_time = int(time.time())
        self._last_send_time = 0.0

    def start(self):
        """Start the background presence updater thread."""
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop, name="DiscordPresenceWorker", daemon=True
            )
            self._worker_thread.start()

    def reload_settings(self):
        """Reload configuration settings from settings handler."""
        with self._lock:
            try:
                self._enabled = bool(config_get("discord_presence"))
                custom_id = str(config_get("discord_client_id") or "").strip()
                new_client_id = custom_id if custom_id else DEFAULT_CLIENT_ID
                self._show_details = bool(config_get("discord_show_details"))
                self._show_buttons = bool(config_get("discord_show_buttons"))
            except Exception:
                pass

            client_id_changed = new_client_id != self._client_id
            self._client_id = new_client_id

            if client_id_changed and self._client:
                self._client.close()
                self._client = None

            self._dirty = True
            self._update_event.set()

    def update_media(
        self,
        title: str,
        channel: str | None = None,
        elapsed: int = 0,
        duration: int = 0,
        is_paused: bool = False,
        url: str | None = None,
        audio_mode: bool = False,
    ):
        """Update presence when media is playing or paused."""
        with self._lock:
            if not self._enabled:
                self._pending_activity = None
                self._dirty = True
                self._update_event.set()
                return

            now = int(time.time())
            activity: dict[str, Any] = {}

            # Details & State
            if self._show_details:
                display_title = title.strip() if title else _("بدون عنوان")
                activity["details"] = truncate_utf8(display_title, MAX_TEXT_BYTES)
                if channel:
                    channel_text = f"by {channel.strip()}"
                    if is_paused:
                        channel_text += f" ({_('متوقف مؤقتًا')})"
                    activity["state"] = truncate_utf8(channel_text, MAX_TEXT_BYTES)
                else:
                    activity["state"] = (
                        truncate_utf8(_("متوقف مؤقتًا"))
                        if is_paused
                        else truncate_utf8(_("قيد التشغيل"))
                    )
            else:
                activity["details"] = truncate_utf8(_("الاستماع عبر HexPlayer"))
                activity["state"] = (
                    truncate_utf8(_("متوقف مؤقتًا"))
                    if is_paused
                    else truncate_utf8(_("قيد التشغيل"))
                )

            # Timestamps
            if not is_paused:
                start_ts = max(0, now - max(0, int(elapsed)))
                timestamps: dict[str, int] = {"start": start_ts}
                if duration and int(duration) > 0 and int(duration) > int(elapsed):
                    timestamps["end"] = start_ts + int(duration)
                activity["timestamps"] = timestamps
            else:
                activity["timestamps"] = {"start": max(0, now - max(0, int(elapsed)))}

            # Assets
            video_id = extract_video_id(url)
            if video_id:
                large_img = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            else:
                large_img = APP_ICON_URL

            small_img = APP_ICON_URL
            small_text = _("متوقف مؤقتًا") if is_paused else _("قيد التشغيل")

            activity["assets"] = {
                "large_image": large_img,
                "large_text": truncate_utf8(
                    f"{application.name} v{application.version}"
                ),
                "small_image": small_img,
                "small_text": truncate_utf8(small_text),
            }

            # Buttons
            if self._show_buttons:
                buttons = []
                if url and url.startswith(("http://", "https://")):
                    btn_label = (
                        _("استماع على يوتيوب") if audio_mode else _("مشاهدة على يوتيوب")
                    )
                    buttons.append(
                        {
                            "label": truncate_utf8(btn_label, MAX_BUTTON_LABEL_BYTES),
                            "url": url,
                        }
                    )
                buttons.append(
                    {
                        "label": truncate_utf8(
                            f"Get {application.name}", MAX_BUTTON_LABEL_BYTES
                        ),
                        "url": application.github_url,
                    }
                )
                if buttons:
                    activity["buttons"] = buttons[:2]

            self._pending_activity = activity
            self._dirty = True
            self._update_event.set()

    def update_idle(self, status_text: str | None = None):
        """Update presence when HexPlayer is browsing or idle."""
        with self._lock:
            if not self._enabled:
                self._pending_activity = None
                self._dirty = True
                self._update_event.set()
                return

            details = status_text or _("تصفح يوتيوب")
            activity = {
                "details": truncate_utf8(details, MAX_TEXT_BYTES),
                "state": truncate_utf8(
                    f"{application.name} v{application.version}", MAX_TEXT_BYTES
                ),
                "timestamps": {"start": self._session_start_time},
                "assets": {
                    "large_image": APP_ICON_URL,
                    "large_text": truncate_utf8(application.name),
                },
            }
            if self._show_buttons:
                activity["buttons"] = [
                    {
                        "label": truncate_utf8(
                            f"Get {application.name}", MAX_BUTTON_LABEL_BYTES
                        ),
                        "url": application.github_url,
                    }
                ]

            self._pending_activity = activity
            self._dirty = True
            self._update_event.set()

    def clear(self):
        """Clear the current Discord activity."""
        with self._lock:
            self._pending_activity = None
            self._dirty = True
            self._update_event.set()

    def shutdown(self):
        """Gracefully stop worker thread and close connection."""
        self._stop_event.set()
        self._update_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        with self._lock:
            if self._client:
                try:
                    self._client.send_activity(None)
                except Exception:
                    pass
                self._client.close()
                self._client = None

    def _worker_loop(self):
        """Worker loop managing connection, reconnect backoff, and activity dispatch."""
        while not self._stop_event.is_set():
            # Wait for event or periodic tick
            self._update_event.wait(timeout=2.0)
            self._update_event.clear()

            if self._stop_event.is_set():
                break

            with self._lock:
                enabled = self._enabled
                client_id = self._client_id
                pending = self._pending_activity
                dirty = self._dirty
                current = self._current_activity

            if not enabled:
                if self._client and self._client.is_connected():
                    self._client.send_activity(None)
                    self._client.close()
                    self._client = None
                with self._lock:
                    self._current_activity = None
                    self._dirty = False
                continue

            # Ensure client exists and connected
            if not self._client or not self._client.is_connected():
                client = DiscordRPCClient(client_id)
                if client.connect():
                    self._client = client
                    logger.debug(
                        "Connected to Discord IPC with Client ID %s", client_id
                    )
                    dirty = True  # Resend state upon reconnect
                else:
                    # Could not connect to Discord (Discord not running)
                    # Wait 10 seconds before retrying
                    self._stop_event.wait(timeout=10.0)
                    continue

            # Dispatch updated activity if dirty
            if dirty or (pending != current):
                now = time.time()
                elapsed_since_send = now - self._last_send_time
                if elapsed_since_send < 1.0:
                    time.sleep(1.0 - elapsed_since_send)

                success = self._client.send_activity(pending)
                self._last_send_time = time.time()
                with self._lock:
                    if success:
                        self._current_activity = pending
                        self._dirty = False
                    else:
                        self._client = None


# Singleton instance
_presence_instance: DiscordPresence | None = None
_instance_lock = threading.Lock()


def get_presence() -> DiscordPresence:
    global _presence_instance
    with _instance_lock:
        if _presence_instance is None:
            _presence_instance = DiscordPresence()
            _presence_instance.reload_settings()
        return _presence_instance


def init_presence():
    """Initialize presence instance, load settings and start background worker."""
    inst = get_presence()
    inst.reload_settings()
    inst.start()
    return inst


def update_media(
    title: str,
    channel: str | None = None,
    elapsed: int = 0,
    duration: int = 0,
    is_paused: bool = False,
    url: str | None = None,
    audio_mode: bool = False,
):
    get_presence().update_media(
        title=title,
        channel=channel,
        elapsed=elapsed,
        duration=duration,
        is_paused=is_paused,
        url=url,
        audio_mode=audio_mode,
    )


def update_idle(status_text: str | None = None):
    get_presence().update_idle(status_text=status_text)


def clear_presence():
    get_presence().clear()


def reload_settings():
    get_presence().reload_settings()


def close_presence():
    global _presence_instance
    with _instance_lock:
        if _presence_instance is not None:
            _presence_instance.shutdown()
            _presence_instance = None
