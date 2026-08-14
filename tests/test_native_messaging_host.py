import json
import struct
from io import BytesIO

import native_messaging_host as host


def encode_native_message(message):
    data = json.dumps(message).encode("utf-8")
    return struct.pack("<I", len(data)) + data


def decode_native_message(payload):
    length = struct.unpack("<I", payload[:4])[0]
    return json.loads(payload[4 : 4 + length].decode("utf-8"))


def test_read_native_message_decodes_framed_json():
    stream = BytesIO(
        encode_native_message(
            {"type": "open", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
    )

    assert host.read_native_message(stream) == {
        "type": "open",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }


def test_write_native_message_encodes_framed_json():
    stream = BytesIO()

    host.write_native_message({"ok": True}, stream)

    assert decode_native_message(stream.getvalue()) == {"ok": True}


def test_handle_message_rejects_unsupported_message_type():
    assert host.handle_message({"type": "ping"}) == {
        "ok": False,
        "error": "Unsupported message type",
    }


def test_launch_or_forward_external_url_uses_ipc_first(monkeypatch):
    calls = []
    monkeypatch.setattr(
        host,
        "send_ipc_message",
        lambda action, url: calls.append((action, url)),
    )

    assert host.launch_or_forward_external_url("https://youtu.be/dQw4w9WgXcQ") is True
    assert calls == [("open_url", "https://youtu.be/dQw4w9WgXcQ")]


def test_launch_or_forward_external_url_starts_gui_when_ipc_fails(monkeypatch):
    started_commands = []
    monkeypatch.setattr(
        host,
        "send_ipc_message",
        lambda *_args: (_ for _ in ()).throw(OSError),
    )
    monkeypatch.setattr(
        host, "get_gui_launch_command", lambda url: ["HexPlayer.exe", url]
    )
    monkeypatch.setattr(host, "start_gui_process", started_commands.append)

    assert (
        host.launch_or_forward_external_url(
            "hexplayer://open?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"
        )
        is True
    )
    assert started_commands == [
        ["HexPlayer.exe", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    ]


def test_launch_or_forward_external_url_rejects_non_youtube(monkeypatch):
    monkeypatch.setattr(
        host,
        "send_ipc_message",
        lambda *_args: (_ for _ in ()).throw(AssertionError),
    )

    assert (
        host.launch_or_forward_external_url("https://example.com/watch?v=test") is False
    )


def test_start_gui_process_detaches_from_native_messaging_pipe(monkeypatch):
    popen_calls = []

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))

    monkeypatch.setattr(host.sys, "platform", "win32")
    monkeypatch.setattr(host.subprocess, "Popen", fake_popen)

    host.start_gui_process(["HexPlayer.exe", "https://youtu.be/dQw4w9WgXcQ"])

    assert popen_calls == [
        (
            ["HexPlayer.exe", "https://youtu.be/dQw4w9WgXcQ"],
            {
                "close_fds": True,
                "stdin": host.subprocess.DEVNULL,
                "stdout": host.subprocess.DEVNULL,
                "stderr": host.subprocess.DEVNULL,
                "creationflags": getattr(host.subprocess, "CREATE_NO_WINDOW", 0),
            },
        )
    ]


def test_handle_message_save_cookies_success(monkeypatch, tmp_path):
    target_path = str(tmp_path / "browser_cookies.txt")
    monkeypatch.setattr(
        "cookies_manager.get_default_browser_cookies_path", lambda: target_path
    )
    saved_settings = {}
    monkeypatch.setattr(
        "settings_handler.config_set", lambda k, v: saved_settings.update({k: v})
    )
    ipc_calls = []
    monkeypatch.setattr(host, "send_ipc_message", lambda a, u: ipc_calls.append((a, u)))

    message = {
        "type": "save_cookies",
        "cookies": [
            {
                "domain": ".youtube.com",
                "name": "LOGIN_INFO",
                "value": "token_123",
                "path": "/",
                "secure": True,
            }
        ],
    }
    response = host.handle_message(message)
    assert response["ok"] is True
    assert response["count"] == 1
    assert saved_settings.get("cookiespath") == target_path
    assert ipc_calls == [("cookies_updated", target_path)]


def test_handle_message_save_cookies_empty():
    response = host.handle_message({"type": "save_cookies", "cookies": []})
    assert response["ok"] is False
    assert "No cookies provided" in response["error"]
