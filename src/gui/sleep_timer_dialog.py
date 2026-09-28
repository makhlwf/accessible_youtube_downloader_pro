import wx

from language_handler import _
from theme_handler import apply_theme


class SleepTimerDialog(wx.Dialog):
    """Accessible dialog to enter a custom sleep-timer duration in minutes."""

    def __init__(self, parent, default_minutes=30):
        wx.Dialog.__init__(self, parent, title=_("مؤقت نوم مخصص"))
        panel = wx.Panel(self)
        label_text = _("عدد الدقائق:")
        label = wx.StaticText(panel, -1, label_text)
        # SpinCtrl: the screen reader announces the value, arrows adjust it, and
        # the user can also type a number directly.
        self.minutesCtrl = wx.SpinCtrl(
            panel, -1, min=1, max=1440, initial=int(default_minutes)
        )
        self.minutesCtrl.SetName(label_text.rstrip(":"))
        okButton = wx.Button(panel, wx.ID_OK, _("مواف&ق"))
        okButton.SetDefault()
        cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إل&غاء"))

        rowSizer = wx.BoxSizer(wx.HORIZONTAL)
        rowSizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        rowSizer.Add(self.minutesCtrl, 1, wx.ALL, 5)

        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer.Add(okButton, 1)
        buttonSizer.Add(cancelButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(rowSizer, 0, wx.EXPAND)
        sizer.Add(buttonSizer, 0, wx.EXPAND)
        panel.SetSizer(sizer)
        sizer.Fit(self)
        self.Centre()
        apply_theme(self)
        self.minutesCtrl.SetFocus()

    def get_minutes(self):
        return int(self.minutesCtrl.GetValue())
