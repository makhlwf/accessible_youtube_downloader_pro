import builtins
import ctypes
import os
import sys
from unittest.mock import MagicMock

# Add application source to sys.path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)


# Mock wx module
class wxWindow:
    def __init__(self, *args, **kwargs):
        self.Parent = kwargs.get("parent", args[0] if args else None)
        self._label = kwargs.get(
            "label", args[2] if len(args) > 2 and isinstance(args[2], str) else ""
        )
        self.Bind = MagicMock()
        self.Freeze = MagicMock()
        self.Thaw = MagicMock()
        self.SetSizer = MagicMock()
        self.SetSizerAndFit = MagicMock()
        self.Layout = MagicMock()
        self.Fit = MagicMock()
        self.SetBackgroundColour = MagicMock()
        self.SetForegroundColour = MagicMock()
        self.GetChildren = MagicMock(return_value=[])
        self.Refresh = MagicMock()
        self.Update = MagicMock()
        self.SetName = MagicMock()
        self.Centre = MagicMock()
        self.Center = MagicMock()
        self.SetSize = MagicMock()
        self.SetMinSize = MagicMock()
        self.Maximize = MagicMock()
        self._is_shown = True
        self._is_enabled = True
        self.Show = lambda show=True: setattr(self, "_is_shown", bool(show))
        self.Hide = lambda: setattr(self, "_is_shown", False)
        self.IsShown = lambda: self._is_shown
        self.Enable = lambda enable=True: setattr(self, "_is_enabled", bool(enable))
        self.Disable = lambda: setattr(self, "_is_enabled", False)
        self.IsEnabled = lambda: self._is_enabled
        self.HasFocus = lambda: getattr(self, "_has_focus", False)
        self.SetFocus = MagicMock()
        self.ShowModal = MagicMock()
        self.ShowFullScreen = MagicMock()
        self.IsFullScreen = MagicMock(return_value=False)
        self.Destroy = MagicMock()
        self.SetAcceleratorTable = MagicMock()
        self.SetMenuBar = MagicMock()
        self.RegisterHotKey = MagicMock()
        self.GetHandle = MagicMock(return_value=12345)
        self.GetParent = lambda: self.Parent
        self.SetTitle = MagicMock()

    def GetLabel(self):
        return self._label

    def SetLabel(self, label):
        self._label = str(label)


_next_control_id = 1000


def _new_control_id():
    global _next_control_id
    _next_control_id += 1
    return _next_control_id


class Frame(wxWindow):
    pass


class Panel(wxWindow):
    pass


class Dialog(wxWindow):
    pass


class Button(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SetDefault = MagicMock()


class StaticText(wxWindow):
    pass


class TextCtrl(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = kwargs.get("value", "")

    def GetValue(self):
        return self._value

    def SetValue(self, val):
        self._value = str(val)

    def ChangeValue(self, val):
        self._value = str(val)

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, val):
        self._value = str(val)


class ListBox(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.Items = list(kwargs.get("choices", []))
        self.Selection = mock_wx.NOT_FOUND

    def Set(self, items):
        self.Items = list(items)

    def Clear(self):
        self.Items = []

    def Append(self, items):
        if isinstance(items, list):
            self.Items.extend(items)
        else:
            self.Items.append(items)

    def GetCount(self):
        return len(self.Items)


class Choice(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._choices = list(kwargs.get("choices", []))
        self._selection = self._choices[0] if self._choices else ""

    def Set(self, items):
        self._choices = list(items)

    def GetStrings(self):
        return self._choices

    def SetStringSelection(self, value):
        self._selection = value

    def GetStringSelection(self):
        return self._selection


class Slider(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id = _new_control_id()
        self._value = kwargs.get("value", 0)

    def GetId(self):
        return self._id

    def SetValue(self, value):
        self._value = value

    def GetValue(self):
        return self._value


class SpinCtrl(wxWindow):
    pass


class SpinCtrlDouble(wxWindow):
    pass


class CheckBox(wxWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = False

    def GetValue(self):
        return self._value

    def SetValue(self, val):
        self._value = bool(val)


class RadioButton(wxWindow):
    pass


class StaticBox(wxWindow):
    pass


class CommandEvent:
    def __init__(self, *args, **kwargs):
        self._int = 0

    def SetInt(self, value):
        self._int = value

    def GetInt(self):
        return self._int


mock_wx = MagicMock()
mock_wx.Frame = Frame
mock_wx.Panel = Panel
mock_wx.Dialog = Dialog
mock_wx.Button = Button
mock_wx.StaticText = StaticText
mock_wx.TextCtrl = TextCtrl
mock_wx.ListBox = ListBox
mock_wx.Choice = Choice
mock_wx.Slider = Slider
mock_wx.SpinCtrl = SpinCtrl
mock_wx.SpinCtrlDouble = SpinCtrlDouble
mock_wx.CheckBox = CheckBox
mock_wx.RadioButton = RadioButton
mock_wx.StaticBox = StaticBox
mock_wx.CommandEvent = CommandEvent
mock_wx.Colour = lambda value: value
mock_wx.SystemSettings = MagicMock()
mock_wx.NullColour = MagicMock()

mock_wx.LANGUAGE_ARABIC = 1
mock_wx.LANGUAGE_ENGLISH = 2
mock_wx.ID_OK = 5100
mock_wx.ID_CANCEL = 5101
mock_wx.YES = 2
mock_wx.NO = 8
mock_wx.ICON_INFORMATION = 4
mock_wx.ICON_ERROR = 256
mock_wx.ICON_WARNING = 1024
mock_wx.OK = 4
mock_wx.CANCEL = 16
mock_wx.TOP = 1
mock_wx.BOTTOM = 2
mock_wx.LEFT = 4
mock_wx.RIGHT = 8
mock_wx.ALL = 15
mock_wx.EXPAND = 8192
mock_wx.VERTICAL = 8
mock_wx.HORIZONTAL = 4
mock_wx.CENTRE = 1
mock_wx.CENTER = 1
mock_wx.ALIGN_CENTER = 1
mock_wx.ALIGN_RIGHT = 2
mock_wx.SL_VERTICAL = 4
mock_wx.NOT_FOUND = -1
mock_wx.Locale = MagicMock()
mock_wx.GetApp = MagicMock()
mock_wx.GetActiveWindow = MagicMock(return_value=None)
mock_wx.GetTopLevelWindows = MagicMock(return_value=[])
mock_wx.Timer = MagicMock()

sys.modules["wx"] = mock_wx
sys.modules["wx.adv"] = MagicMock()
sys.modules["wx.lib"] = MagicMock()
mock_newevent = MagicMock()
mock_newevent.NewEvent.return_value = (MagicMock(), MagicMock())
sys.modules["wx.lib.newevent"] = mock_newevent

# Mock ctypes for non-Windows environments
if not hasattr(ctypes, "windll"):
    mock_ctypes = MagicMock()
    sys.modules["ctypes"] = mock_ctypes


# Mock other problematic modules if necessary
class MockType(type):
    def __instancecheck__(cls, instance):
        return True


class Playlist(metaclass=MockType):
    pass


class VideosSearch(metaclass=MockType):
    pass


class PlaylistsSearch(metaclass=MockType):
    pass


class ChannelsSearch(metaclass=MockType):
    pass


mock_py_yt = MagicMock()
mock_py_yt.Playlist = Playlist
mock_py_yt.VideosSearch = VideosSearch
mock_py_yt.PlaylistsSearch = PlaylistsSearch
mock_py_yt.ChannelsSearch = ChannelsSearch
sys.modules["py_yt"] = mock_py_yt
sys.modules["pyperclip"] = MagicMock()

import pytest


@pytest.fixture(autouse=True)
def reset_gettext():
    builtins._ = lambda x: x
    yield
    builtins._ = lambda x: x


if not hasattr(builtins, "_"):
    builtins._ = lambda x: x
