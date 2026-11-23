import wx

from language_handler import _
from speech_client import speak
from theme_handler import apply_theme


class DownloadProgress(wx.Frame):
    def __init__(self, parent, title=""):
        wx.Frame.__init__(self, parent=parent)
        self.Title = _("جاري التنزيل - {}").format(
            title if title != "" else "accessible youtube downloader pro"
        )
        self.cancelled = False
        self.finished = False
        self.cancel_callback = None
        self.Centre()
        panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self.textProgress = wx.Choice(
            panel,
            -1,
            choices=[
                _("نسبة التنزيل: {}%").format(0),
                _("حجم الملف الإجمالي: غير معروف"),
                _("مقدار الحجم الذي تم تنزيله: غير معروف"),
                _("الوقت المتبقي: غير معروف"),
                _("سرعة التنزيل: غير معروفة"),
            ],
        )
        self.textProgress.Selection = 0
        self.gaugeProgress = wx.Gauge(panel, -1, range=100)
        self.cancel_button = wx.Button(panel, wx.ID_CANCEL, _("إلغاء"))
        self.cancel_button.Bind(wx.EVT_BUTTON, lambda event: self.Close())
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.textProgress, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.gaugeProgress, 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self.cancel_button, 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)
        self.Fit()
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        apply_theme(self)

    def set_cancel_callback(self, callback):
        self.cancel_callback = callback

    def is_cancelled(self):
        return self.cancelled

    def mark_finished(self):
        self.finished = True

    def on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()

    def onClose(self, event):
        if self.finished:
            self.Destroy()
            return
        if not event.CanVeto():
            self.Destroy()
            return
        event.Veto()
        if self.cancelled:
            return
        message = wx.MessageBox(
            _("هناك عملية تنزيل جارية. هل تريد إلغاءها؟"),
            _("إنهاء"),
            style=wx.YES_NO,
            parent=self,
        )
        if message == wx.YES:
            self.cancelled = True
            status = _("جاري إلغاء التنزيل...")
            self.textProgress.SetString(0, status)
            speak(status, interrupt=True)
            self.gaugeProgress.Disable()
            if self.cancel_callback:
                self.cancel_callback()
