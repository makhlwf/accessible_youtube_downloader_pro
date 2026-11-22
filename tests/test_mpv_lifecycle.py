import ctypes
import threading
import zipfile
from unittest.mock import Mock

import pytest

from media_player import mpv_backend
from media_player.mpv_backend import MpvEvent, MpvEventEndFile, MpvMediaPlayer, State


@pytest.fixture
def player(monkeypatch):
    lib = Mock()
    lib.mpv_create.return_value = 1
    lib.mpv_client_api_version.return_value = 0x00020005
    lib.mpv_set_option_string.return_value = 0
    lib.mpv_initialize.return_value = 0
    lib.mpv_command_node.return_value = 0
    lib.mpv_set_property.return_value = 0
    lib.mpv_get_property.return_value = -1
    lib.mpv_wait_event.side_effect = lambda *args: None
    monkeypatch.setattr(mpv_backend, "_load_mpv", lambda: lib)
    # Drive events explicitly to control their ordering.
    monkeypatch.setattr(MpvMediaPlayer, "_event_loop", lambda self: None)
    instance = MpvMediaPlayer()
    yield instance
    instance._event_thread = None
    instance.close()


def _send_event(player, event_id, data=None):
    pointer = (
        ctypes.cast(ctypes.pointer(data), ctypes.c_void_p) if data is not None else None
    )
    return player._handle_event(MpvEvent(event_id, 0, 0, pointer))


def test_play_during_opening_does_not_replace_the_pending_file(player):
    player.set_media(mpv_backend.MpvMedia("first"))
    player.play()
    player.play()

    assert player.get_state() == State.Opening
    player._lib.mpv_command_node.assert_called_once()


def test_replaced_file_events_cannot_finish_or_seek_new_media(player, monkeypatch):
    monkeypatch.setattr(
        mpv_backend, "_parse_node", lambda node: {"playlist_entry_id": 2}
    )
    media = mpv_backend.MpvMedia("second")
    player.set_media(media)
    player.play()
    player.set_time(1500)
    player.set_position(0.25)

    _send_event(player, mpv_backend.MPV_EVENT_START_FILE, ctypes.c_int64(1))
    _send_event(player, mpv_backend.MPV_EVENT_FILE_LOADED)
    old_eof = MpvEventEndFile(mpv_backend.MPV_END_FILE_REASON_EOF, 0, 1)
    assert _send_event(player, mpv_backend.MPV_EVENT_END_FILE, old_eof) is None
    assert player.get_state() == State.Opening
    player._lib.mpv_command.assert_not_called()

    _send_event(player, mpv_backend.MPV_EVENT_START_FILE, ctypes.c_int64(2))
    _send_event(player, mpv_backend.MPV_EVENT_FILE_LOADED)
    player._lib.mpv_command.assert_called_once()
    command = player._lib.mpv_command.call_args.args[1]
    assert list(command) == [b"seek", b"25.0", b"absolute-percent", b"exact", None]
    eof = MpvEventEndFile(mpv_backend.MPV_END_FILE_REASON_EOF, 0, 2)
    end_event = _send_event(player, mpv_backend.MPV_EVENT_END_FILE, eof)
    assert end_event.media is media
    assert player.get_state() == State.Ended


def test_current_file_startup_error_is_reported(player, monkeypatch):
    monkeypatch.setattr(
        mpv_backend, "_parse_node", lambda node: {"playlist_entry_id": 2}
    )
    media = mpv_backend.MpvMedia("broken")
    player.set_media(media)
    player.play()

    error = MpvEventEndFile(mpv_backend.MPV_END_FILE_REASON_ERROR, -13, 2)
    event = _send_event(player, mpv_backend.MPV_EVENT_END_FILE, error)
    assert event.reason == mpv_backend.MPV_END_FILE_REASON_ERROR
    assert event.error == -13
    assert event.media is media
    assert player.get_state() == State.Error


def test_shutdown_leaves_handle_alive_until_event_loop_exits(monkeypatch):
    lib = Mock()
    lib.mpv_create.return_value = 1
    lib.mpv_client_api_version.return_value = 0x00020005
    lib.mpv_set_option_string.return_value = 0
    lib.mpv_initialize.return_value = 0
    waiting = threading.Event()
    released = threading.Event()

    def wait_event(handle, timeout):
        waiting.set()
        released.wait(5)

    lib.mpv_wait_event.side_effect = wait_event
    monkeypatch.setattr(mpv_backend, "_load_mpv", lambda: lib)
    player = MpvMediaPlayer()
    event_thread = player._event_thread
    try:
        assert waiting.wait(2)
        with monkeypatch.context() as patch:
            patch.setattr(event_thread, "join", lambda timeout: None)
            player.close()
        lib.mpv_terminate_destroy.assert_not_called()
        player.get_time()
        lib.mpv_get_property.assert_not_called()
    finally:
        released.set()
        event_thread.join(2)
    lib.mpv_terminate_destroy.assert_called_once_with(1)


def test_dll_extraction_only_publishes_the_complete_file(tmp_path, monkeypatch):
    dll_path = tmp_path / "libmpv-2.dll"
    with zipfile.ZipFile(tmp_path / "libmpv-2.dll.zip", "w") as archive:
        archive.writestr(dll_path.name, b"bundled binary")

    def copy(source, destination):
        destination.write(source.read(1))
        destination.flush()
        assert not dll_path.exists()
        destination.write(source.read())

    monkeypatch.setattr(mpv_backend.shutil, "copyfileobj", copy)

    assert mpv_backend._extract_mpv_dll(tmp_path) == dll_path
    assert dll_path.read_bytes() == b"bundled binary"
    assert list(tmp_path.glob("*.tmp")) == []
