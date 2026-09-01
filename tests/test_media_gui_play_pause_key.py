from unittest.mock import MagicMock, patch

import wx

from media_player import media_gui
from media_player.media_gui import MediaGui


class MockKeyEvent:
    """Key event that records whether the handler let the key through."""

    def __init__(self, key_code):
        self._key_code = key_code
        self.skipped = None

    def ShiftDown(self):
        return False

    def ControlDown(self):
        return False

    def HasAnyModifiers(self):
        return False

    def GetKeyCode(self):
        return self._key_code

    def GetUnicodeKey(self):
        return 0

    def Skip(self, val=True):
        self.skipped = bool(val)


def _make_gui():
    gui = MediaGui.__new__(MediaGui)
    gui._is_context_menu_key = lambda evt: False
    return gui


def test_space_toggles_playback_once_and_consumes_key():
    gui = _make_gui()
    evt = MockKeyEvent(wx.WXK_SPACE)

    with patch.object(gui, "playAction") as mock_play:
        gui.onKeyDown(evt)
        mock_play.assert_called_once()

    # The key must not reach a focused control button, which would activate it
    # and toggle playback a second time.
    assert evt.skipped is False


def test_pause_key_toggles_playback_once_and_consumes_key():
    gui = _make_gui()
    evt = MockKeyEvent(wx.WXK_PAUSE)

    with patch.object(gui, "playAction") as mock_play:
        gui.onKeyDown(evt)
        mock_play.assert_called_once()

    assert evt.skipped is False


def test_initial_focus_is_the_frame_not_a_control_button():
    mock_stream = MagicMock()
    mock_stream.url = "http://fake.stream/url"
    mock_stream.headers = {}
    mock_stream.audio_url = None

    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.speak"),
        patch.object(media_gui, "config_get", return_value=0),
    ):
        gui = MediaGui(
            parent=None,
            title="Video",
            stream=mock_stream,
            url="http://youtube.com/watch?v=abc",
            can_download=True,
        )

        gui.SetFocus.assert_called_once()
        for control in gui._player_controls:
            control.SetFocus.assert_not_called()

        gui.closeAction()
