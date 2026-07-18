import json
import os
import socket
import struct
import subprocess
import sys

from youtube_url_utils import extract_launch_youtube_url

IPC_HOST = "127.0.0.1"
IPC_PORT = 57280
GUI_EXE_NAME = "HexPlayer.exe"
MAX_MESSAGE_SIZE = 1024 * 1024


def read_native_message(stdin=None):
    stdin = stdin or sys.stdin.buffer
    raw_length = stdin.read(4)
    if len(raw_length) == 0:
        return None
    if len(raw_length) != 4:
        raise ValueError("Invalid native message length header")

    message_length = struct.unpack("<I", raw_length)[0]
    if message_length > MAX_MESSAGE_SIZE:
        raise ValueError("Native message is too large")

    data = stdin.read(message_length)
    if len(data) != message_length:
        raise ValueError("Incomplete native message")

    return json.loads(data.decode("utf-8"))


def write_native_message(message, stdout=None):
    stdout = stdout or sys.stdout.buffer
    data = json.dumps(message).encode("utf-8")
    stdout.write(struct.pack("<I", len(data)))
    stdout.write(data)
    stdout.flush()


def send_ipc_message(action, url=""):
    payload = json.dumps({"action": action, "url": url}).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        sock.connect((IPC_HOST, IPC_PORT))
        sock.sendall(payload)


def get_gui_launch_command(url):
    if getattr(sys, "frozen", False):
        app_path = os.path.join(os.path.dirname(sys.executable), GUI_EXE_NAME)
        if os.path.exists(app_path):
            return [app_path, url]
        return [sys.executable, url]

    app_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "accessible_youtube_downloader_pro.py",
    )
    return [sys.executable, app_script, url]


def start_gui_process(command):
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
        start_gui_process(get_gui_launch_command(url))
        return True
    except Exception:
        return False


def handle_message(message):
    if not isinstance(message, dict):
        return {"ok": False, "error": "Invalid message"}
    if message.get("type") != "open":
        return {"ok": False, "error": "Unsupported message type"}

    opened = launch_or_forward_external_url(message.get("url", ""))
    return {"ok": opened}


def main():
    try:
        message = read_native_message()
        if message is None:
            return 1
        response = handle_message(message)
        write_native_message(response)
        return 0 if response.get("ok") else 1
    except Exception as exc:
        try:
            write_native_message({"ok": False, "error": str(exc)})
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
