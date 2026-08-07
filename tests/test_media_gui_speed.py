import wx

from media_player import media_gui


class MockMedia:
    def __init__(self, rate=1.0):
        self._rate = rate

    def get_rate(self):
        return self._rate

    def set_rate(self, rate):
        self._rate = rate


class MockPlayer:
    def __init__(self, rate=1.0):
        self.media = MockMedia(rate)


class MockKeyEvent:
    def __init__(self, key_code, shift_down=False, unicode_key=0):
        self._key_code = key_code
        self._shift_down = shift_down
        self._unicode_key = unicode_key

    def ShiftDown(self):
        return self._shift_down

    def ControlDown(self):
        return False

    def HasAnyModifiers(self):
        return self._shift_down

    def GetKeyCode(self):
        return self._key_code

    def GetUnicodeKey(self):
        return self._unicode_key

    def Skip(self, val=True):
        pass


def test_speed_increase_shortcut(monkeypatch):
    spoken = []
    monkeypatch.setattr(media_gui, "speak", lambda msg: spoken.append(msg))
    monkeypatch.setattr(
        media_gui,
        "config_get",
        lambda key: 0.05 if key == "playback_speed_step" else None,
    )

    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._is_context_menu_key = lambda evt: False
    gui.player = MockPlayer(1.0)

    # Shift + . (keycode ord('.'))
    evt = MockKeyEvent(ord("."), shift_down=True, unicode_key=ord(">"))
    gui.onKeyDown(evt)

    assert gui.player.media.get_rate() == 1.05
    assert spoken == ["1.05x"]


def test_speed_decrease_shortcut(monkeypatch):
    spoken = []
    monkeypatch.setattr(media_gui, "speak", lambda msg: spoken.append(msg))
    monkeypatch.setattr(
        media_gui,
        "config_get",
        lambda key: 0.05 if key == "playback_speed_step" else None,
    )

    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._is_context_menu_key = lambda evt: False
    gui.player = MockPlayer(1.0)

    # Shift + , (keycode ord(','))
    evt = MockKeyEvent(ord(","), shift_down=True, unicode_key=ord("<"))
    gui.onKeyDown(evt)

    assert gui.player.media.get_rate() == 0.95
    assert spoken == ["0.95x"]


def test_old_speed_shortcuts_disabled(monkeypatch):
    spoken = []
    monkeypatch.setattr(media_gui, "speak", lambda msg: spoken.append(msg))
    monkeypatch.setattr(
        media_gui,
        "config_get",
        lambda key: 0.05 if key == "playback_speed_step" else None,
    )

    gui = media_gui.MediaGui.__new__(media_gui.MediaGui)
    gui._is_context_menu_key = lambda evt: False
    gui.player = MockPlayer(1.0)

    # Shift + Up should no longer change speed
    evt_up = MockKeyEvent(wx.WXK_UP, shift_down=True)
    gui.onKeyDown(evt_up)
    assert gui.player.media.get_rate() == 1.0
    assert spoken == []

    # Shift + Down should no longer change speed
    evt_down = MockKeyEvent(wx.WXK_DOWN, shift_down=True)
    gui.onKeyDown(evt_down)
    assert gui.player.media.get_rate() == 1.0
    assert spoken == []
