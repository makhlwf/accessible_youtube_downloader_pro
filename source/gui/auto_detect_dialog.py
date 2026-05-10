import wx
from language_handler import _
from theme_handler import apply_theme

from media_player.media_gui import MediaGui
from utils import get_audio_stream
from nvda_client.client import speak


def link_type(url):
    cases = ("list", "channel", "playlist", "/user/")
    if cases[0] in url or cases[2] in url:
        return _("قائمة تشغيل")
    elif cases[1] in url or cases[3] in url:
        return _("قناة")
    else:
        return _("فيديو")


class AutoDetectDialog(wx.Dialog):
    def __init__(self, parent, url):
        wx.Dialog.__init__(
            self,
            None,
            title=parent.Title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP,
        )
        self.url = url
        self.Centre()
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        content_sizer = wx.BoxSizer(wx.VERTICAL)

        text = wx.StaticText(
            panel,
            -1,
            _(
                "لقد تم الكشف عن وجود رابط ل{} يوتيوب في الحافظة. يرجى اختيار الإجراء المطلوب"
            ).format(link_type(url)),
        )
        content_sizer.Add(text, 0, wx.ALL | wx.CENTER, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        downloadButton = wx.Button(panel, -1, _("تنزيل"))
        playButton = wx.Button(panel, -1, _("تشغيل"))

        if link_type(self.url) == _("قائمة تشغيل"):
            playButton.Label = _("فتح...")
        elif link_type(url) != _("فيديو"):
            playButton.Disable()

        cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إلغاء"))

        btn_sizer.Add(downloadButton, 0, wx.ALL, 5)
        btn_sizer.Add(playButton, 0, wx.ALL, 5)
        btn_sizer.Add(cancelButton, 0, wx.ALL, 5)

        content_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        panel.SetSizer(content_sizer)

        main_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(main_sizer)
        apply_theme(self)

        downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        playButton.Bind(wx.EVT_BUTTON, self.onPlay)

    def onDownload(self, event):
        from .download_dialog import DownloadDialog

        main_window = wx.GetApp().GetTopWindow()
        if not main_window.IsShown():
            main_window.Show()
        dlg = DownloadDialog(main_window, self.url)
        dlg.Show()
        main_window.Raise()
        self.Destroy()

    def onPlay(self, event):
        from .playlist_dialog import PlaylistDialog

        main_window = wx.GetApp().GetTopWindow()
        if not main_window.IsShown():
            main_window.Show()
        main_window.Raise()

        if link_type(self.url) == _("قائمة تشغيل"):
            PlaylistDialog(main_window, self.url)
            self.Destroy()
            return
        from .activity_dialog import LoadingDialog

        self.Destroy()
        stream = LoadingDialog(
            main_window, _("جاري التشغيل"), get_audio_stream, self.url
        ).res
        if stream:
            MediaGui(main_window, stream.title, stream, self.url)
        else:
            speak(_("تعذر جلب بيانات المقطع"))
