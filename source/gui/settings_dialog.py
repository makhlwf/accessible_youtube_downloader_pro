import os
import sys

import wx
from language_handler import _
from settings_handler import config_get, config_set
from language_handler import supported_languages


languages = {
    index: language for language, index in enumerate(supported_languages.values())
}


class SettingsDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title=_("الإعدادات"))
        self.SetSize(500, 500)
        self.Centre()
        self.preferences = {}
        panel = wx.Panel(self)
        lbl = wx.StaticText(panel, -1, _("لغة البرنامج: "), name="language")
        self.languageBox = wx.Choice(panel, -1, name="language")
        self.languageBox.Set(list(supported_languages.keys()))
        try:
            self.languageBox.Selection = languages[config_get("lang")]
        except KeyError:
            self.languageBox.Selection = 0
        wx.StaticText(panel, -1, _("مسار مجلد التنزيل: "), name="path")
        self.pathField = wx.TextCtrl(
            panel,
            -1,
            value=config_get("path"),
            name="path",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        changeButton = wx.Button(panel, -1, _("&تغيير المسار"), name="path")
        wx.StaticText(panel, -1, _("مسار ملف الكوكيز: "), name="cookies")
        self.cookiesPathField = wx.TextCtrl(
            panel,
            -1,
            value=config_get("cookiespath"),
            name="cookies",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        changeCookiesButton = wx.Button(panel, -1, _("تغيير"), name="cookies")
        clearCookiesButton = wx.Button(panel, -1, _("حذف"), name="cookies")
        preferencesBox = wx.StaticBox(panel, -1, _("التفضيلات العامة"))
        self.autoDetectItem = wx.CheckBox(
            preferencesBox,
            -1,
            _("اكتشاف الروابط تلقائيًا عند فتح البرنامج"),
            name="autodetect",
        )
        self.autoCheckForUpdates = wx.CheckBox(
            preferencesBox,
            -1,
            _("الكشف عن التحديثات الجديدة تلقائيًا عند فتح البرنامج"),
            name="checkupdates",
        )
        self.autoLoadItem = wx.CheckBox(
            preferencesBox,
            -1,
            _(
                "تحميل المزيد من نتائج البحث عند الوصول إلى نهاية قائمة الفيديوهات المعروضة"
            ),
            name="autoload",
        )
        self.autoCheckForUpdates.SetValue(config_get("checkupdates"))
        self.autoDetectItem.SetValue(config_get("autodetect"))
        self.autoLoadItem.SetValue(config_get("autoload"))
        downloadPreferencesBox = wx.StaticBox(panel, -1, _("إعدادات التنزيل"))
        lbl2 = wx.StaticText(downloadPreferencesBox, -1, _("صيغة التحميل المباشر: "))
        self.formats = wx.Choice(
            downloadPreferencesBox,
            -1,
            choices=[_("فيديو (mp4)"), _("صوت (m4a)"), _("صوت (mp3)")],
        )
        self.formats.Selection = int(config_get("defaultformat"))
        lbl3 = wx.StaticText(downloadPreferencesBox, -1, _("جودة تحويل ملفات mp3: "))
        self.mp3Quality = wx.Choice(
            downloadPreferencesBox,
            -1,
            choices=["96 kbps", "128 kbps", "192 kbps"],
            name="conversion",
        )
        self.mp3Quality.Selection = int(config_get("conversion"))
        playerOptions = wx.StaticBox(panel, -1, _("إعدادات المشغل"))
        self.videoQualityLabel = wx.StaticText(
            playerOptions, -1, _("جودة الفيديو الافتراضية: ")
        )
        self.videoQuality = wx.Choice(
            playerOptions,
            -1,
            choices=["144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"],
        )
        self.videoQuality.Selection = int(config_get("defaultvideoquality"))
        self.audioQualityLabel = wx.StaticText(
            playerOptions, -1, _("جودة الصوت الافتراضية: ")
        )
        self.audioQuality = wx.Choice(
            playerOptions,
            -1,
            choices=[_("منخفضة"), _("متوسطة"), _("عالية")],
        )
        self.audioQuality.Selection = int(config_get("defaultaudioquality"))
        self.continueWatching = wx.CheckBox(
            playerOptions,
            -1,
            _("متابعة المشاهدة بعد إغلاق الفيديو وتشغيله من جديد"),
            name="continue",
        )
        self.continueWatching.Value = config_get("continue")
        self.repeateTracks = wx.CheckBox(
            playerOptions,
            -1,
            _("إعادة تشغيل المقطع تلقائيًا عند انتهائه"),
            name="repeatetracks",
        )
        self.autoPlayNext = wx.CheckBox(
            playerOptions,
            -1,
            _("الانتقال إلى المقطع التالي تلقائيًا عند انتهاء المقطع الحالي"),
            name="autonext",
        )
        self.autoPlayNext.Value = config_get("autonext")
        self.repeateTracks.Value = config_get("repeatetracks")
        okButton = wx.Button(panel, wx.ID_OK, _("مواف&ق"), name="ok_cancel")
        okButton.SetDefault()
        wx.Button(panel, wx.ID_CANCEL, _("إل&غاء"), name="ok_cancel")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer3 = wx.BoxSizer(wx.HORIZONTAL)
        sizer4 = wx.BoxSizer(wx.VERTICAL)
        sizer5 = wx.BoxSizer(wx.HORIZONTAL)
        sizer6 = wx.BoxSizer(wx.HORIZONTAL)
        cookiesSizer = wx.BoxSizer(wx.HORIZONTAL)
        okCancelSizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(lbl, 1)
        sizer1.Add(self.languageBox, 1, wx.EXPAND)
        for control in panel.GetChildren():
            if control.Name == "ok_cancel":
                okCancelSizer.Add(control, 1)
            elif control.Name == "path":
                sizer2.Add(control, 1)
            elif control.Name == "cookies":
                cookiesSizer.Add(control, 1)
        for item in preferencesBox.GetChildren():
            sizer3.Add(item, 1)
        preferencesBox.SetSizer(sizer3)
        sizer5.Add(lbl3, 1)
        sizer5.Add(self.mp3Quality, 1)
        sizer6.Add(lbl2, 1)
        sizer6.Add(self.formats, 1)
        sizer4.Add(sizer5)
        sizer4.Add(sizer6)
        downloadPreferencesBox.SetSizer(sizer4)
        playerOptionsSizer = wx.BoxSizer(wx.VERTICAL)
        videoQualitySizer = wx.BoxSizer(wx.HORIZONTAL)
        audioQualitySizer = wx.BoxSizer(wx.HORIZONTAL)
        videoQualitySizer.Add(self.videoQualityLabel, 1)
        videoQualitySizer.Add(self.videoQuality, 1)
        audioQualitySizer.Add(self.audioQualityLabel, 1)
        audioQualitySizer.Add(self.audioQuality, 1)
        playerOptionsSizer.Add(videoQualitySizer, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(audioQualitySizer, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(self.continueWatching, 0, wx.ALL, 5)
        playerOptionsSizer.Add(self.repeateTracks, 0, wx.ALL, 5)
        playerOptionsSizer.Add(self.autoPlayNext, 0, wx.ALL, 5)
        playerOptions.SetSizer(playerOptionsSizer)
        sizer.Add(sizer1, 1, wx.EXPAND)
        sizer.Add(sizer2, 1, wx.EXPAND)
        sizer.Add(cookiesSizer, 1, wx.EXPAND)
        sizer.Add(preferencesBox, 1, wx.EXPAND)
        sizer.Add(downloadPreferencesBox, 1, wx.EXPAND)
        sizer.Add(playerOptions, 1, wx.EXPAND)
        sizer.Add(okCancelSizer, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        changeButton.Bind(wx.EVT_BUTTON, self.onChange)
        changeCookiesButton.Bind(wx.EVT_BUTTON, self.onChangeCookies)
        clearCookiesButton.Bind(wx.EVT_BUTTON, self.onClearCookies)
        self.autoDetectItem.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoLoadItem.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoCheckForUpdates.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.repeateTracks.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoPlayNext.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.continueWatching.Bind(wx.EVT_CHECKBOX, self.onCheck)
        okButton.Bind(wx.EVT_BUTTON, self.onOk)
        self.ShowModal()

    def onCheck(self, event):
        obj = event.EventObject
        if all((self.repeateTracks.Value, self.autoPlayNext.Value)) and obj in (
            self.repeateTracks,
            self.autoPlayNext,
        ):
            self.repeateTracks.Value = self.autoPlayNext.Value = False
        if obj.Name in self.preferences and config_get(obj.Name) == obj.Value:
            del self.preferences[obj.Name]
        elif not obj.Value == config_get(obj.Name):
            self.preferences[obj.Name] = obj.Value

    def onChange(self, event):
        new = wx.DirSelector(
            _("اختر مجلد التنزيل"),
            os.path.join(os.getenv("userprofile"), "downloads"),
            parent=self,
        )
        if not new == "":
            self.preferences["path"] = new
            self.pathField.Value = new
            self.pathField.SetFocus()

    def onChangeCookies(self, event):
        wildcard = "Text Files (*.txt)|*.txt"
        dlg = wx.FileDialog(
            self,
            message=_("اختر ملف الكوكيز"),
            defaultDir=os.getcwd(),
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_CHANGE_DIR,
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.preferences["cookiespath"] = path
            self.cookiesPathField.Value = path
            self.cookiesPathField.SetFocus()
        dlg.Destroy()

    def onClearCookies(self, event):
        self.preferences["cookiespath"] = ""
        self.cookiesPathField.Value = ""

    def onOk(self, event):
        for key, item in self.preferences.items():
            config_set(key, item)
        if not self.mp3Quality.Selection == int(config_get("conversion")):
            config_set("conversion", self.mp3Quality.Selection)
        config_set(
            "defaultformat", self.formats.Selection
        ) if not self.formats.Selection == int(config_get("defaultformat")) else None
        config_set("defaultvideoquality", self.videoQuality.Selection)
        config_set("defaultaudioquality", self.audioQuality.Selection)
        lang = {value: key for key, value in languages.items()}
        if not lang[self.languageBox.Selection] == config_get("lang"):
            config_set("lang", lang[self.languageBox.Selection])
            msg = wx.MessageBox(
                _(
                    "لقد قمت بتغيير لغة البرنامج إلى {}, مما يعني أنه ينبغي عليك إعادة تشغيل البرنامج لتطبيق التعديلات. هل تريد القيام بذلك حالًا?"
                ).format(self.languageBox.StringSelection),
                _("تنبيه"),
                style=wx.YES_NO,
                parent=self,
            )
            os.execl(sys.executable, sys.executable, *sys.argv) if msg == 2 else None
        self.Destroy()
