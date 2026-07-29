import os
import subprocess

import wx

from language_handler import _
from theme_handler import apply_theme


class DownloadCompleteDialog(wx.Dialog):
    def __init__(self, parent, file_path=None, folder_path=None):
        super().__init__(parent, title=_("اكتمل التنزيل"))
        self.file_path = file_path
        self.folder_path = folder_path or (
            os.path.dirname(file_path) if file_path else None
        )
        self.CentreOnParent()

        panel = wx.Panel(self)
        message = wx.StaticText(panel, -1, _("اكتمل التنزيل بنجاح."))
        close_button = wx.Button(panel, wx.ID_OK, _("موافق"))
        close_button.SetDefault()

        buttons = []
        if self.file_path and os.path.exists(self.file_path):
            play_button = wx.Button(panel, -1, _("تشغيل الملف الذي تم تنزيله"))
            show_button = wx.Button(panel, -1, _("إظهار الملف في مستكشف الملفات"))
            play_button.Bind(wx.EVT_BUTTON, self.on_play)
            show_button.Bind(wx.EVT_BUTTON, self.on_show_file)
            buttons.extend([play_button, show_button])
        elif self.folder_path and os.path.isdir(self.folder_path):
            open_folder_button = wx.Button(panel, -1, _("فتح مجلد التنزيل"))
            open_folder_button.Bind(wx.EVT_BUTTON, self.on_open_folder)
            buttons.append(open_folder_button)
        buttons.append(close_button)

        sizer = wx.BoxSizer(wx.VERTICAL)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(message, 0, wx.EXPAND | wx.ALL, 8)
        for button in buttons:
            button_sizer.Add(button, 1, wx.EXPAND | wx.ALL, 4)
        sizer.Add(button_sizer, 0, wx.EXPAND)
        panel.SetSizer(sizer)
        self.Fit()
        self.Bind(wx.EVT_CHAR_HOOK, self.on_hook)
        apply_theme(self)

    def on_play(self, event):
        os.startfile(self.file_path)
        self.EndModal(wx.ID_OK)

    def on_show_file(self, event):
        subprocess.Popen(["explorer", "/select,", self.file_path])
        self.EndModal(wx.ID_OK)

    def on_open_folder(self, event):
        os.startfile(self.folder_path)
        self.EndModal(wx.ID_OK)

    def on_hook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK)
            return
        event.Skip()


def show_download_complete(parent, file_path=None, folder_path=None):
    dialog = DownloadCompleteDialog(
        parent, file_path=file_path, folder_path=folder_path
    )
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()
