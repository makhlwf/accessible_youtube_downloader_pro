from threading import Thread

import wx

import utils
from gui.channel_dialog import ChannelDialog
from language_handler import _
from speech_client import speak
from theme_handler import apply_theme


class SubscriptionsDialog(wx.Frame):
    """Lists the channels the logged-in user is subscribed to.

    Each entry shows the channel name and its subscriber count; activating an
    entry opens that channel in the in-app channel browser (ChannelDialog).
    Requires a valid cookies file — the home screen only offers this window
    when cookies are configured.
    """

    def __init__(self, parent):
        wx.Frame.__init__(self, parent=parent, title=_("القنوات المشترك بها"))
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.panel = wx.Panel(self)

        lbl = wx.StaticText(self.panel, -1, _("القنوات التي تشترك بها في يوتيوب:"))
        self.channelsList = wx.ListBox(self.panel, -1, name=_("القنوات المشترك بها"))

        self.openButton = wx.Button(
            self.panel, -1, _("فتح القناة\tenter"), name="controls"
        )
        backButton = wx.Button(self.panel, -1, _("العودة إلى النافذة الرئيسية"))

        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(backButton, 1, wx.ALL)

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        for control in self.panel.GetChildren():
            if control.Name == "controls":
                sizer2.Add(control, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(sizer1, 0, wx.EXPAND)
        sizer.Add(lbl, 0, wx.ALL, 5)
        sizer.Add(self.channelsList, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(sizer2, 0, wx.EXPAND | wx.ALL, 5)
        self.panel.SetSizer(sizer)
        apply_theme(self)

        self.openButton.Bind(wx.EVT_BUTTON, lambda event: self.open_channel())
        backButton.Bind(wx.EVT_BUTTON, lambda event: self.backAction())
        self.Bind(
            wx.EVT_LISTBOX_DCLICK, lambda event: self.open_channel(), self.channelsList
        )
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)

        self.channels = []
        self.load_channels()
        self.Show()
        self.Parent.Hide()

    def load_channels(self):
        self.channelsList.Set([_("جاري تحميل قائمة القنوات... يرجى الانتظار")])
        speak(_("جاري تحميل قائمة القنوات المشترك بها"))

        def _load():
            data = utils.get_subscribed_channels(parent=self)
            wx.CallAfter(self._update_channels, data)

        Thread(target=_load, daemon=True).start()

    def _update_channels(self, data):
        error = data.get("error") if isinstance(data, dict) else None
        if error:
            wx.MessageBox(
                error,
                _("تنبيه"),
                style=wx.OK | wx.ICON_WARNING,
                parent=self,
            )
            speak(error)
            self.channelsList.Set([_("تعذر تحميل قائمة القنوات")])
            self.channelsList.SetFocus()
            return

        self.channels = data.get("channels") or [] if isinstance(data, dict) else []
        if not self.channels:
            self.channelsList.Set([_("لا توجد قنوات مشترك بها")])
            speak(_("لا توجد قنوات مشترك بها"))
            self.channelsList.SetFocus()
            return

        titles = []
        for channel in self.channels:
            name = channel.get("name") or _("غير معروف")
            subscribers = channel.get("subscribers") or ""
            if subscribers:
                titles.append(f"{name}, {subscribers}")
            else:
                titles.append(name)
        self.channelsList.Set(titles)
        if self.channels:
            self.channelsList.SetSelection(0)
        speak(_("تم تحميل {count} قناة").format(count=len(self.channels)))
        self.channelsList.SetFocus()

    def open_channel(self):
        selection = self.channelsList.GetSelection()
        if selection == wx.NOT_FOUND or not self.channels:
            return
        if selection >= len(self.channels):
            return
        channel = self.channels[selection]
        url = channel.get("url")
        if not url:
            return
        ChannelDialog(self, url, channel.get("name") or _("قناة"))

    def backAction(self):
        self.Parent.Show()
        self.Destroy()

    def onClose(self, event):
        self.backAction()

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.backAction()
        elif event.KeyCode == wx.WXK_RETURN and self.FindFocus() == self.channelsList:
            self.open_channel()
        else:
            event.Skip()
