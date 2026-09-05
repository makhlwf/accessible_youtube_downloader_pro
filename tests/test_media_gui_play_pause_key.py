from unittest.mock import MagicMock, patch

import wx

from media_player import media_gui
from media_player.media_gui import MediaGui


class MockKeyEvent:
    """Key event that records whether the handler let the key through."""

    def __init__(
        self, key_code, ctrl_down=False, shift_down=False, alt_down=False, unicode_key=0
    ):
        self._key_code = key_code
        self._ctrl_down = ctrl_down
        self._shift_down = shift_down
        self._alt_down = alt_down
        self._unicode_key = unicode_key
        self.skipped = None

    def ShiftDown(self):
        return self._shift_down

    def ControlDown(self):
        return self._ctrl_down

    def AltDown(self):
        return self._alt_down

    def HasAnyModifiers(self):
        return self._ctrl_down or self._shift_down or self._alt_down

    def GetKeyCode(self):
        return self._key_code

    def GetUnicodeKey(self):
        return self._unicode_key

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


def test_ctrl_b_opens_browser_and_consumes_key():
    gui = _make_gui()
    evt = MockKeyEvent(ord("B"), ctrl_down=True)

    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt)
        mock_browser.assert_called_once_with(evt)

    assert evt.skipped is False


def test_plain_b_or_ctrl_shift_b_does_not_open_browser():
    gui = _make_gui()

    evt_plain = MockKeyEvent(ord("B"), ctrl_down=False)
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt_plain)
        mock_browser.assert_not_called()
    assert evt_plain.skipped is not False

    evt_shift = MockKeyEvent(ord("B"), ctrl_down=True, shift_down=True)
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt_shift)
        mock_browser.assert_not_called()
    assert evt_shift.skipped is not False


def test_ctrl_b_in_suggestions_key_down_opens_browser():
    gui = _make_gui()
    evt = MockKeyEvent(ord("B"), ctrl_down=True)

    with patch.object(gui, "onBrowser") as mock_browser:
        gui.on_suggestions_key_down(evt)
        mock_browser.assert_called_once_with(evt)

    assert evt.skipped is False


def test_ctrl_lowercase_b_and_unicode_b_open_browser():
    gui = _make_gui()

    evt_lower = MockKeyEvent(ord("b"), ctrl_down=True)
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt_lower)
        mock_browser.assert_called_once_with(evt_lower)
    assert evt_lower.skipped is False

    evt_unicode = MockKeyEvent(0, ctrl_down=True, unicode_key=ord("b"))
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt_unicode)
        mock_browser.assert_called_once_with(evt_unicode)
    assert evt_unicode.skipped is False

    evt_sug_lower = MockKeyEvent(ord("b"), ctrl_down=True)
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.on_suggestions_key_down(evt_sug_lower)
        mock_browser.assert_called_once_with(evt_sug_lower)
    assert evt_sug_lower.skipped is False

    evt_sug_unicode = MockKeyEvent(0, ctrl_down=True, unicode_key=ord("B"))
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.on_suggestions_key_down(evt_sug_unicode)
        mock_browser.assert_called_once_with(evt_sug_unicode)
    assert evt_sug_unicode.skipped is False


def test_ctrl_alt_b_does_not_open_browser():
    gui = _make_gui()
    evt_alt = MockKeyEvent(ord("B"), ctrl_down=True, alt_down=True)
    with patch.object(gui, "onBrowser") as mock_browser:
        gui.onKeyDown(evt_alt)
        mock_browser.assert_not_called()
    assert evt_alt.skipped is not False


def test_on_browser_safe_when_no_url():
    gui = _make_gui()
    gui.url = None
    with (
        patch("media_player.media_gui.webbrowser.open") as mock_open,
        patch("media_player.media_gui.speak") as mock_speak,
    ):
        gui.onBrowser()
        mock_open.assert_not_called()
        mock_speak.assert_not_called()


def test_on_browser_opens_url_and_speaks_when_url_present():
    gui = _make_gui()
    gui.url = "https://www.youtube.com/watch?v=example"
    with (
        patch("media_player.media_gui.webbrowser.open") as mock_open,
        patch("media_player.media_gui.speak") as mock_speak,
    ):
        gui.onBrowser()
        mock_speak.assert_called_once()
        mock_open.assert_called_once_with("https://www.youtube.com/watch?v=example")
