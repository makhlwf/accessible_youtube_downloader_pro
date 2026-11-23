"""Native messaging when the desktop executable is launched as the host."""

import logging
import os
import subprocess
import sys

from app_runtime.ipc import send_ipc_message
from app_state import settings_handler
from native_messaging_host import read_native_message, write_native_message
from youtube_backend.youtube_url_utils import extract_launch_youtube_url

logger = logging.getLogger(__name__)


def is_native_messaging_invocation(argv):
    return "--native-messaging-host" in argv or any(
        arg.startswith("chrome-extension://") for arg in argv[1:]
    )


def start_detached_process(command):
    kwargs = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(command, **kwargs)


def launch_or_forward_external_url(url):
    url = extract_launch_youtube_url(url)
    if not url:
        return False

    try:
        send_ipc_message("open_url", url)
        return True
    except Exception:
        pass

    try:
        if getattr(sys, "frozen", False):
            start_detached_process([sys.executable, url])
        else:
            script_path = os.path.abspath(sys.modules["__main__"].__file__)
            start_detached_process([sys.executable, script_path, url])
        return True
    except Exception as e:
        logger.error("Failed to launch HexPlayer from native host: %s", e)
        return False


def native_messaging_main():
    try:
        message = read_native_message()
        if not isinstance(message, dict):
            write_native_message({"ok": False, "error": "Invalid message"})
            return 1
        msg_type = message.get("type")
        if msg_type == "open":
            url = message.get("url", "")
            opened = launch_or_forward_external_url(url)
            write_native_message({"ok": opened})
            return 0 if opened else 1
        elif msg_type == "save_cookies":
            cookies = message.get("cookies", [])
            from youtube_backend import cookies_manager

            result = cookies_manager.save_raw_browser_cookies(cookies)
            if result.get("success"):
                settings_handler.config_set("cookiespath", result["path"])
                try:
                    send_ipc_message("cookies_updated", result["path"])
                except Exception:
                    pass
                write_native_message(
                    {
                        "ok": True,
                        "count": result.get("count", 0),
                        "path": result.get("path", ""),
                    }
                )
                return 0
            write_native_message(
                {"ok": False, "error": result.get("error", "Failed to save cookies")}
            )
            return 1

        write_native_message({"ok": False, "error": "Unsupported message type"})
        return 1
    except Exception as e:
        try:
            write_native_message({"ok": False, "error": str(e)})
        except Exception:
            pass
        return 1
