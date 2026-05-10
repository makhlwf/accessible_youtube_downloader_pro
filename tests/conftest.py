import sys
import os
import ctypes
import builtins
from unittest.mock import MagicMock

# Add source to sys.path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source"))
)


# Mock wx module
class wxWindow:
    def __init__(self, *args, **kwargs):
        self.Bind = MagicMock()
        self.SetSizer = MagicMock()
        self.SetSizerAndFit = MagicMock()
        self.Layout = MagicMock()
        self.Fit = MagicMock()
        self.SetBackgroundColour = MagicMock()
        self.SetForegroundColour = MagicMock()
        self.GetChildren = MagicMock(return_value=[])
        self.Refresh = MagicMock()
        self.Update = MagicMock()


class Frame(wxWindow):
    pass


class Panel(wxWindow):
    pass


class Dialog(wxWindow):
    pass


class Button(wxWindow):
    pass


class StaticText(wxWindow):
    pass


class TextCtrl(wxWindow):
    pass


class ListBox(wxWindow):
    pass


class Choice(wxWindow):
    pass


class SpinCtrl(wxWindow):
    pass


class SpinCtrlDouble(wxWindow):
    pass


class CheckBox(wxWindow):
    pass


class RadioButton(wxWindow):
    pass


class StaticBox(wxWindow):
    pass


mock_wx = MagicMock()
mock_wx.Frame = Frame
mock_wx.Panel = Panel
mock_wx.Dialog = Dialog
mock_wx.Button = Button
mock_wx.StaticText = StaticText
mock_wx.TextCtrl = TextCtrl
mock_wx.ListBox = ListBox
mock_wx.Choice = Choice
mock_wx.SpinCtrl = SpinCtrl
mock_wx.SpinCtrlDouble = SpinCtrlDouble
mock_wx.CheckBox = CheckBox
mock_wx.RadioButton = RadioButton
mock_wx.StaticBox = StaticBox
mock_wx.Colour = MagicMock
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
mock_wx.ALIGN_CENTER = 1
mock_wx.NOT_FOUND = -1
mock_wx.Locale = MagicMock()
mock_wx.GetApp = MagicMock()
mock_wx.Timer = MagicMock()

sys.modules["wx"] = mock_wx
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


mock_py_yt = MagicMock()
mock_py_yt.Playlist = Playlist
mock_py_yt.VideosSearch = VideosSearch
mock_py_yt.PlaylistsSearch = PlaylistsSearch
sys.modules["py_yt"] = mock_py_yt
sys.modules["vlc"] = MagicMock()
sys.modules["pyperclip"] = MagicMock()

# Mock builtins._ for translation
builtins._ = lambda x: x
