import os

import pyperclip
import wx

import utils
from download_handler.downloader import (
    downloadAction,
    get_audio_download_format,
    get_video_download_format,
)
from language_handler import _
from settings_handler import config_get, config_set
from theme_handler import apply_theme

from .download_progress import DownloadProgress


class DownloadDialog(wx.Frame):
    def __init__(self, parent, default_url=""):
        wx.Frame.__init__(self, parent=parent, title=_("تنزيل"))
        self.path = config_get("path")
        self.Centre()
        self.downloading = False
        self.panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self.panel, -1, _("رابط التنزيل: : "))
        self.videoLink = wx.TextCtrl(self.panel, -1, value=default_url)
        self.downloadingFormat = wx.RadioBox(
            self.panel, -1, _("نوع المقطع"), choices=[_("صوت"), _("فيديو")]
        )
        lbl2 = wx.StaticText(self.panel, -1, _("صيغة المقطع"), name="convert")
        self.convertingFormat = wx.Choice(
            self.panel, -1, choices=["m4a", "mp3"], name="convert"
        )
        self.convertingFormat.SetSelection(int(config_get("defaultaudio")))
        self.downloadButton = wx.Button(self.panel, -1, _("تنزيل"))
        self.downloadButton.SetDefault()
        self.changePath = wx.Button(
            self.panel, -1, f"{_('مسار مجلد التنزيل: ')} {self.path}"
        )
        self.changePath.Bind(wx.EVT_BUTTON, self.onChangePath)
        sizer1.Add(lbl, 1)
        sizer1.Add(self.videoLink, 1, wx.EXPAND)
        sizer.Add(sizer1, 1, wx.EXPAND)
        sizer.Add(self.downloadingFormat, 1, wx.EXPAND)
        sizer2.Add(lbl2)
        sizer2.Add(self.convertingFormat, 1, wx.EXPAND)
        sizer.Add(sizer2, 1, wx.EXPAND)
        sizer.Add(self.downloadButton, 1, wx.EXPAND)
        sizer.Add(self.changePath, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)
        # event bindings
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.Bind(wx.EVT_ACTIVATE, self.onActivate)
        self.Bind(wx.EVT_RADIOBOX, self.onRadioBox)
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        apply_theme(self)

    # a method to show/hide the audio formats box depending on the downloading type
    def toggleChoices(self):
        for control in self.panel.GetChildren():
            if self.downloadingFormat.Selection == 0 and control.Name == "convert":
                control.Show()
            elif self.downloadingFormat.Selection == 1 and control.Name == "convert":
                control.Hide()

    # an event method which is called when the radio box selection is changed
    def onRadioBox(self, event):
        self.toggleChoices()

    # an event method to call the detect clipboard function when activating the window
    def onActivate(self, event):
        if not self.downloading:
            self.detectFromClipboard()
        else:
            self.downloading = False
        event.Skip()

    # changing path button action
    def onChangePath(self, event):
        path = wx.DirSelector(
            _("اختر مجلد التنزيل"),
            os.path.join(os.getenv("userprofile"), "downloads"),
            parent=self,
        )  # folder select dialog
        if path == "":
            return
        self.changePath.SetLabel(
            f"{_('مسار مجلد التنزيل: ')} {path}"
        )  # editing the change path label to show the new path
        self.path = path

    # detect youtube links from the clipboard function
    def detectFromClipboard(self):
        clip_content = pyperclip.paste()  # get the clipboard content
        detected_url = utils.extract_supported_youtube_url(clip_content)
        if detected_url and not utils.is_supported_youtube_url(self.videoLink.Value):
            self.videoLink.SetValue(detected_url)

    def onDownload(self, event):
        url = self.videoLink.GetValue()
        if url == "" or not utils.is_supported_youtube_url(url):
            utils.show_error(_("يرجى إدخال رابطًا صحيحًا."), parent=self)
            wx.CallAfter(self.videoLink.SetFocus)
            return
        cases = ("list", "channel", "playlist", "/user/", "/c/", "/@", "RD", "mix")
        for case in cases:
            if case in url:
                folder = True
                break
        else:
            folder = False
        formats = {
            0: get_audio_download_format(convert=self.convertingFormat.Selection == 1),
            1: get_video_download_format(),
        }
        format = formats[self.downloadingFormat.GetSelection()]
        if (
            self.downloadingFormat.Selection == 0
            and self.convertingFormat.Selection == 1
        ):
            convert = True
        else:
            convert = False

        if not utils.check_yt_dlp(self):
            return

        config_set("defaultaudio", str(self.convertingFormat.Selection))
        downloadFrame = DownloadProgress(wx.GetApp().GetTopWindow())
        started = downloadAction(
            url,
            self.path,
            downloadFrame,
            format,
            downloadFrame.gaugeProgress,
            downloadFrame.textProgress,
            convert=convert,
            folder=folder,
        )
        if started:
            self.downloading = True
            self.Destroy()

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.Destroy()
        event.Skip()
