"""Unit tests for Discord Rich Presence module."""

import json
import socket
import struct
from unittest.mock import MagicMock, patch

import discord_presence
from discord_presence import (
    OP_FRAME,
    OP_HANDSHAKE,
    DiscordPresence,
    DiscordRPCClient,
    extract_video_id,
    truncate_utf8,
)

# ============================================================================
# 1. Helper function tests
# ============================================================================


def test_truncate_utf8_ascii():
    text = "Short text"
    assert truncate_utf8(text, 128) == "Short text"


def test_truncate_utf8_long_ascii():
    text = "a" * 200
    res = truncate_utf8(text, 128)
    assert len(res.encode("utf-8")) <= 128
    assert res == "a" * 128


def test_truncate_utf8_multibyte():
    # Arabic text: 2 bytes per char
    text = "قناة اليوتيوب الرسمية للاعبين"
    encoded = text.encode("utf-8")
    assert len(encoded) > 20

    # Truncate at 21 bytes (an odd boundary that might split a 2-byte character)
    truncated = truncate_utf8(text, 21)
    truncated_bytes = truncated.encode("utf-8")
    assert len(truncated_bytes) <= 21
    # Verify it decodes cleanly without replacement errors
    assert truncated_bytes.decode("utf-8") == truncated


def test_truncate_utf8_empty():
    assert truncate_utf8("", 128) == ""
    assert truncate_utf8(None, 128) == ""


def test_truncate_utf8_single_char_pads_space():
    # Discord requires length >= 2
    res = truncate_utf8("a", 128)
    assert len(res) >= 2


def test_extract_video_id():
    assert (
        extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtube.com/shorts/abcdefghijk") == "abcdefghijk"
    assert (
        extract_video_id("https://www.youtube.com/embed/12345678901") == "12345678901"
    )
    assert (
        extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=share"
        )
        == "dQw4w9WgXcQ"
    )
    assert extract_video_id("https://example.com/not-youtube") is None
    assert extract_video_id("") is None
    assert extract_video_id(None) is None


# ============================================================================
# 2. DiscordRPCClient low-level IPC tests
# ============================================================================


def test_client_init():
    client = DiscordRPCClient("123456789")
    assert client.client_id == "123456789"
    assert client.stream is None
    assert client.is_connected() is False


def test_client_connect_and_handshake_windows():
    client = DiscordRPCClient("123456789")
    mock_file = MagicMock()

    # Mock response from Discord: Opcode 1 (FRAME) with JSON response
    resp_payload = json.dumps({"cmd": "DISPATCH", "evt": "READY"}).encode("utf-8")
    header = struct.pack("<II", 1, len(resp_payload))
    mock_file.read.side_effect = [header, resp_payload]

    with patch("sys.platform", "win32"), patch("builtins.open", return_value=mock_file):
        assert client.connect() is True
        assert client.is_connected() is True

    # Verify handshake packet was written
    mock_file.write.assert_called_once()
    written_data = mock_file.write.call_args[0][0]
    opcode, _length = struct.unpack("<II", written_data[:8])
    assert opcode == OP_HANDSHAKE
    payload = json.loads(written_data[8:].decode("utf-8"))
    assert payload["client_id"] == "123456789"
    assert payload["v"] == 1


def test_client_connect_and_handshake_linux():
    client = DiscordRPCClient("123456789")
    mock_file = MagicMock()

    resp_payload = json.dumps({"cmd": "DISPATCH", "evt": "READY"}).encode("utf-8")
    header = struct.pack("<II", 1, len(resp_payload))
    mock_file.read.side_effect = [header, resp_payload]

    mock_sock = MagicMock()
    mock_sock.makefile.return_value = mock_file

    with (
        patch("sys.platform", "linux"),
        patch.object(socket, "AF_UNIX", 1, create=True),
        patch("os.path.exists", return_value=True),
        patch("socket.socket", return_value=mock_sock),
    ):
        assert client.connect() is True
        assert client.is_connected() is True

    mock_file.write.assert_called_once()
    written_data = mock_file.write.call_args[0][0]
    opcode, _length = struct.unpack("<II", written_data[:8])
    assert opcode == OP_HANDSHAKE
    payload = json.loads(written_data[8:].decode("utf-8"))
    assert payload["client_id"] == "123456789"
    assert payload["v"] == 1


def test_client_send_activity():
    client = DiscordRPCClient("123456789")
    mock_file = MagicMock()
    client.stream = mock_file

    resp_payload = json.dumps({"cmd": "SET_ACTIVITY", "data": {}}).encode("utf-8")
    header = struct.pack("<II", 1, len(resp_payload))
    mock_file.read.side_effect = [header, resp_payload]

    activity = {
        "details": "Test Song",
        "state": "Test Artist",
        "assets": {"large_image": "test_img"},
    }
    result = client.send_activity(activity)
    assert result is True

    # Verify SET_ACTIVITY packet
    mock_file.write.assert_called_once()
    written_data = mock_file.write.call_args[0][0]
    opcode, _length = struct.unpack("<II", written_data[:8])
    assert opcode == OP_FRAME
    payload = json.loads(written_data[8:].decode("utf-8"))
    assert payload["cmd"] == "SET_ACTIVITY"
    assert payload["args"]["activity"]["details"] == "Test Song"


def test_client_close():
    client = DiscordRPCClient("123456789")
    mock_file = MagicMock()
    client.stream = mock_file

    client.close()
    assert client.is_connected() is False
    mock_file.close.assert_called_once()


def test_client_send_failure_disconnects():
    client = DiscordRPCClient("123456789")
    mock_file = MagicMock()
    mock_file.write.side_effect = OSError("Pipe broken")
    client.stream = mock_file

    result = client.send_activity({"details": "Fail"})
    assert result is False
    assert client.is_connected() is False


# ============================================================================
# 3. DiscordPresence high-level manager tests
# ============================================================================


def test_presence_disabled_via_settings():
    with patch("discord_presence.config_get") as mock_config:
        mock_config.side_effect = lambda key, default=None: {
            "discord_presence": False,
            "discord_client_id": "",
        }.get(key, default)

        presence = DiscordPresence()
        presence.reload_settings()
        assert not presence._enabled

        # Calling update_media or update_idle should clear pending activity
        presence.update_media(title="Test")
        assert presence._pending_activity is None

        presence.update_idle()
        assert presence._pending_activity is None


def test_presence_media_payload_full():
    presence = DiscordPresence()
    presence._enabled = True
    presence._show_details = True
    presence._show_buttons = True

    presence.update_media(
        title="Awesome Music Track",
        channel="Amazing Channel",
        elapsed=120,
        duration=300,
        is_paused=False,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        audio_mode=False,
    )

    activity = presence._pending_activity
    assert activity is not None
    assert activity["details"] == "Awesome Music Track"
    assert "Amazing Channel" in activity["state"]
    assert "timestamps" in activity
    assert "end" in activity["timestamps"]
    assert (
        activity["assets"]["large_image"]
        == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    )
    assert len(activity["buttons"]) == 2
    assert (
        activity["buttons"][0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert activity["buttons"][1]["label"] == "Download HexPlayer"


def test_presence_media_payload_channel_as_dict():
    presence = DiscordPresence()
    presence._enabled = True
    presence._show_details = True

    presence.update_media(
        title="Song with Dict Channel",
        channel={"name": "My Channel Name", "url": "https://youtube.com/@mychannel"},
    )
    activity = presence._pending_activity
    assert activity is not None
    assert "My Channel Name" in activity["state"]


def test_presence_media_payload_paused():
    presence = DiscordPresence()
    presence._enabled = True
    presence._show_details = True
    presence._show_buttons = True

    presence.update_media(
        title="Awesome Music Track",
        channel="Amazing Channel",
        elapsed=60,
        duration=180,
        is_paused=True,
        url=None,
        audio_mode=True,
    )

    activity = presence._pending_activity
    assert activity is not None
    assert activity["details"] == "Awesome Music Track"
    # Paused tracks do not show countdown end timestamp
    assert "end" not in activity.get("timestamps", {})


def test_presence_media_payload_privacy_mode():
    """When show_details and show_buttons are False, hide title, channel, and buttons."""
    presence = DiscordPresence()
    presence._enabled = True
    presence._show_details = False
    presence._show_buttons = False

    presence.update_media(
        title="Top Secret Video",
        channel="Secret Channel",
        elapsed=60,
        duration=180,
        is_paused=False,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        audio_mode=False,
    )

    activity = presence._pending_activity
    assert activity is not None
    assert "Top Secret Video" not in activity["details"]
    assert "Secret Channel" not in activity.get("state", "")
    assert "buttons" not in activity


def test_presence_idle_payload():
    presence = DiscordPresence()
    presence._enabled = True

    presence.update_idle(status_text="In Main Menu")
    activity = presence._pending_activity
    assert activity is not None
    assert activity["details"] == "In Main Menu"
    assert "timestamps" in activity
    assert "start" in activity["timestamps"]


def test_presence_reload_settings():
    with patch("discord_presence.config_get") as mock_config:
        mock_config.side_effect = lambda key, default=None: {
            "discord_presence": True,
            "discord_client_id": "999999999",
            "discord_show_details": True,
            "discord_show_buttons": False,
        }.get(key, default)

        presence = DiscordPresence()
        presence._enabled = False
        presence._client_id = "old_id"

        presence.reload_settings()
        assert presence._enabled is True
        assert presence._client_id == "999999999"
        assert presence._show_buttons is False


def test_presence_clear():
    presence = DiscordPresence()
    presence._pending_activity = {"details": "Active"}
    presence.clear()
    assert presence._pending_activity is None


def test_module_convenience_functions():
    with patch("discord_presence.get_presence") as mock_get_presence:
        mock_inst = MagicMock()
        mock_get_presence.return_value = mock_inst

        discord_presence.update_idle("Testing")
        mock_inst.update_idle.assert_called_once_with(status_text="Testing")

        discord_presence.update_media(title="Test", channel="Ch")
        mock_inst.update_media.assert_called_once()

        discord_presence.clear_presence()
        mock_inst.clear.assert_called_once()

        discord_presence.reload_settings()
        mock_inst.reload_settings.assert_called_once()

        inst = discord_presence.init_presence()
        mock_inst.start.assert_called_once()
        assert inst == mock_inst
