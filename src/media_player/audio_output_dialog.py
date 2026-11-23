"""Audio output device selection for the media player."""

import wx

from gui.theme_handler import apply_theme
from language_handler import _


class AudioOutputDeviceDialog(wx.Dialog):
    def __init__(self, parent, devices, selected_device):
        wx.Dialog.__init__(self, parent, title=_("جهاز إخراج الصوت"))
        self.SetSize(450, 200)
        self.Centre()
        self.devices = [{"id": "", "description": _("جهاز إخراج الصوت الافتراضي")}]
        self.devices.extend(devices)

        panel = wx.Panel(self)
        label = wx.StaticText(panel, -1, _("جهاز إخراج الصوت: "))
        self.deviceBox = wx.Choice(
            panel,
            -1,
            choices=[device["description"] for device in self.devices],
        )
        self.deviceBox.Selection = self.get_selection_for_device(selected_device)
        okButton = wx.Button(panel, wx.ID_OK, _("مواف&ق"))
        okButton.SetDefault()
        cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إل&غاء"))

        deviceSizer = wx.BoxSizer(wx.HORIZONTAL)
        deviceSizer.Add(label, 1)
        deviceSizer.Add(self.deviceBox, 2, wx.EXPAND)

        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer.Add(okButton, 1)
        buttonSizer.Add(cancelButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(deviceSizer, 1, wx.EXPAND)
        sizer.Add(buttonSizer, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        apply_theme(self)

    def get_selection_for_device(self, selected_device):
        for index, device in enumerate(self.devices):
            if device["id"] == selected_device:
                return index
        return 0

    def get_selected_device(self):
        return self.devices[self.deviceBox.Selection]
