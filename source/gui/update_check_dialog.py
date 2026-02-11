import wx
from language_handler import _
import application

class UpdateCheckDialog(wx.Dialog):
    def __init__(self, parent, new_version, whats_new):
        super().__init__(parent, title=_("تحديث جديد متوفر"))
        self.new_version = new_version
        self.whats_new = whats_new
        self.InitUI()
        self.Center()

    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        info_text = _("هناك تحديث جديد متوفر للتطبيق.")
        st1 = wx.StaticText(panel, label=info_text)
        vbox.Add(st1, 0, wx.ALL, 10)

        version_info = _("الإصدار الحالي: {current}\nالإصدار الجديد: {new}").format(
            current=application.version, new=self.new_version
        )
        st2 = wx.StaticText(panel, label=version_info)
        vbox.Add(st2, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        whats_new_label = wx.StaticText(panel, label=_("ما الجديد:"))
        vbox.Add(whats_new_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.whats_new_text = wx.TextCtrl(
            panel,
            value=self.whats_new,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
            size=(400, 200),
        )
        vbox.Add(self.whats_new_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.download_btn = wx.Button(panel, label=_("تنزيل"), id=wx.ID_OK)
        self.download_btn.SetDefault()
        self.cancel_btn = wx.Button(panel, label=_("إلغاء"), id=wx.ID_CANCEL)
        hbox.Add(self.download_btn)
        hbox.Add(self.cancel_btn, flag=wx.LEFT, border=5)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 10)

        panel.SetSizer(vbox)
        vbox.Fit(self)
