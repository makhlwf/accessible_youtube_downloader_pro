import wx
import wx.adv
from language_handler import _


class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        icon = wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_MENU)
        self.SetIcon(icon, _("HexPlayer"))

        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_show)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        show_item = menu.Append(-1, _("عرض البرنامج"))
        exit_item = menu.Append(-1, _("خروج"))

        self.Bind(wx.EVT_MENU, self.on_show, show_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)

        return menu

    def on_show(self, event):
        if not self.frame.IsShown():
            self.frame.Show()
        self.frame.Raise()
        self.frame.SetFocus()

    def on_exit(self, event):
        self.frame.Close()
