import os
import sys

import wx
from language_handler import _, supported_languages
from settings_handler import config_get, config_set
from theme_handler import THEMES, apply_theme
import windows_url_association


languages = {
    index: language for language, index in enumerate(supported_languages.values())
}

DEFAULT_AUDIO_OUTPUT_DEVICE = ""


def _theme_labels():
    return {
        "System Default": _("افتراضي النظام"),
        "Light": _("فاتح"),
        "Dark": _("داكن"),
        "High Contrast Dark": _("تباين عال داكن"),
    }


def _normalise_audio_output_device(device_id):
    if device_id is None or device_id == "None":
        return DEFAULT_AUDIO_OUTPUT_DEVICE
    return str(device_id)


def _get_audio_output_device_choices():
    devices = [
        {
            "id": DEFAULT_AUDIO_OUTPUT_DEVICE,
            "description": _("جهاز إخراج الصوت الافتراضي"),
        }
    ]
    try:
        from media_player.mpv_backend import get_available_audio_output_devices

        devices.extend(get_available_audio_output_devices())
    except Exception:
        pass

    selected_device = _normalise_audio_output_device(config_get("audiooutputdevice"))
    if selected_device and not any(
        device["id"] == selected_device for device in devices
    ):
        devices.append({"id": selected_device, "description": selected_device})
    return devices


class SettingsDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title=_("الإعدادات"))
        self.SetMinSize((560, 520))
        self.SetSize((760, 680))
        self.Centre()
        self.preferences = {}
        self.theme_keys = list(THEMES.keys())
        self.theme_labels = _theme_labels()
        panel = wx.ScrolledWindow(self)
        panel.SetScrollRate(8, 8)

        lbl = wx.StaticText(panel, -1, _("لغة البرنامج: "), name="language")
        self.languageBox = wx.Choice(panel, -1, name="language")
        self.languageBox.Set(list(supported_languages.keys()))
        try:
            self.languageBox.Selection = languages[config_get("lang")]
        except KeyError:
            self.languageBox.Selection = 0
        self.pathField = wx.TextCtrl(
            panel,
            -1,
            value=config_get("path"),
            name="path",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        changeButton = wx.Button(panel, -1, _("&تغيير المسار"), name="path")
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
        self.debugMode = wx.CheckBox(
            preferencesBox,
            -1,
            _("تفعيل رسائل تصحيح الأخطاء للمطورين فقط"),
            name="debug",
        )
        self.backgroundMonitoring = wx.CheckBox(
            preferencesBox,
            -1,
            _("التشغيل في الخلفية ومراقبة الحافظة عند بدء تشغيل النظام"),
            name="background_monitoring",
        )
        self.browserIntegration = wx.CheckBox(
            preferencesBox,
            -1,
            _("تفعيل التكامل الآمن مع إضافة المتصفح"),
            name="browser_integration",
        )
        self.autoCheckForUpdates.SetValue(config_get("checkupdates"))
        self.autoDetectItem.SetValue(config_get("autodetect"))
        self.autoLoadItem.SetValue(config_get("autoload"))
        self.debugMode.SetValue(config_get("debug"))
        self.backgroundMonitoring.SetValue(config_get("background_monitoring"))
        self.browserIntegration.SetValue(config_get("browser_integration"))
        if sys.platform != "win32":
            self.browserIntegration.Disable()
        theme_label = wx.StaticText(preferencesBox, -1, _("مظهر البرنامج: "))
        self.themeBox = wx.Choice(
            preferencesBox,
            -1,
            name="theme",
            choices=[
                self.theme_labels.get(theme, theme) for theme in self.theme_keys
            ],
        )
        try:
            self.themeBox.Selection = self.theme_keys.index(config_get("theme"))
        except ValueError:
            self.themeBox.Selection = 0

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
            choices=[_("96 ك.ب/ث"), _("128 ك.ب/ث"), _("192 ك.ب/ث")],
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
            choices=[
                _("144ب"),
                _("240ب"),
                _("360ب"),
                _("480ب"),
                _("720ب"),
                _("1080ب"),
                _("1440ب"),
                _("2160ب"),
            ],
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
        self.audioOutputDevices = _get_audio_output_device_choices()
        self.audioOutputDeviceLabel = wx.StaticText(
            playerOptions, -1, _("جهاز إخراج الصوت: ")
        )
        self.audioOutputDevice = wx.Choice(
            playerOptions,
            -1,
            choices=[device["description"] for device in self.audioOutputDevices],
        )
        self.audioOutputDevice.Selection = self.getAudioOutputDeviceSelection(
            config_get("audiooutputdevice")
        )
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
            name="repeatTracks",
        )
        self.autoPlayNext = wx.CheckBox(
            playerOptions,
            -1,
            _("الانتقال إلى المقطع التالي تلقائيًا عند انتهاء المقطع الحالي"),
            name="autonext",
        )
        self.autoPlayNext.Value = config_get("autonext")
        self.repeateTracks.Value = config_get("repeatTracks")
        self.eqButton = wx.Button(playerOptions, -1, _("إعدادات المعادل..."))
        self.playbackSpeedStepLabel = wx.StaticText(
            playerOptions, -1, _("مقدار تغيير سرعة التشغيل: ")
        )
        self.playbackSpeedStep = wx.SpinCtrlDouble(
            playerOptions,
            -1,
            value=str(config_get("playback_speed_step")),
            min=0.01,
            max=1.0,
            inc=0.01,
        )
        okButton = wx.Button(panel, wx.ID_OK, _("مواف&ق"), name="ok_cancel")
        okButton.SetDefault()
        wx.Button(panel, wx.ID_CANCEL, _("إل&غاء"), name="ok_cancel")

        def add_row(sizer, label, control):
            sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
            sizer.Add(control, 1, wx.EXPAND | wx.ALL, 5)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        general_grid = wx.FlexGridSizer(0, 2, 6, 8)
        general_grid.AddGrowableCol(1, 1)
        add_row(general_grid, lbl, self.languageBox)

        path_controls = wx.BoxSizer(wx.HORIZONTAL)
        self.pathField.SetMinSize((-1, 56))
        path_controls.Add(self.pathField, 1, wx.EXPAND | wx.RIGHT, 5)
        path_controls.Add(changeButton, 0, wx.EXPAND)
        path_label = wx.StaticText(panel, -1, _("مسار مجلد التنزيل: "))
        add_row(general_grid, path_label, path_controls)

        cookies_controls = wx.BoxSizer(wx.HORIZONTAL)
        self.cookiesPathField.SetMinSize((-1, 56))
        cookies_controls.Add(self.cookiesPathField, 1, wx.EXPAND | wx.RIGHT, 5)
        cookies_controls.Add(changeCookiesButton, 0, wx.EXPAND | wx.RIGHT, 5)
        cookies_controls.Add(clearCookiesButton, 0, wx.EXPAND)
        cookies_label = wx.StaticText(panel, -1, _("مسار ملف الكوكيز: "))
        add_row(general_grid, cookies_label, cookies_controls)
        main_sizer.Add(general_grid, 0, wx.EXPAND | wx.ALL, 8)

        preferencesSizer = wx.BoxSizer(wx.VERTICAL)
        for item in (
            self.autoDetectItem,
            self.autoCheckForUpdates,
            self.autoLoadItem,
            self.debugMode,
            self.backgroundMonitoring,
            self.browserIntegration,
        ):
            preferencesSizer.Add(item, 0, wx.EXPAND | wx.ALL, 5)
        theme_sizer = wx.BoxSizer(wx.HORIZONTAL)
        theme_sizer.Add(theme_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        theme_sizer.Add(self.themeBox, 1, wx.EXPAND)
        preferencesSizer.Add(theme_sizer, 0, wx.EXPAND | wx.ALL, 5)
        preferencesBox.SetSizer(preferencesSizer)
        main_sizer.Add(preferencesBox, 0, wx.EXPAND | wx.ALL, 8)

        download_grid = wx.FlexGridSizer(0, 2, 6, 8)
        download_grid.AddGrowableCol(1, 1)
        add_row(download_grid, lbl2, self.formats)
        add_row(download_grid, lbl3, self.mp3Quality)
        downloadPreferencesBox.SetSizer(download_grid)
        main_sizer.Add(downloadPreferencesBox, 0, wx.EXPAND | wx.ALL, 8)

        playerOptionsSizer = wx.BoxSizer(wx.VERTICAL)
        player_grid = wx.FlexGridSizer(0, 2, 6, 8)
        player_grid.AddGrowableCol(1, 1)
        add_row(player_grid, self.videoQualityLabel, self.videoQuality)
        add_row(player_grid, self.audioQualityLabel, self.audioQuality)
        add_row(player_grid, self.audioOutputDeviceLabel, self.audioOutputDevice)
        add_row(player_grid, self.playbackSpeedStepLabel, self.playbackSpeedStep)
        playerOptionsSizer.Add(player_grid, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(self.continueWatching, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(self.repeateTracks, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(self.autoPlayNext, 0, wx.EXPAND | wx.ALL, 5)
        playerOptionsSizer.Add(self.eqButton, 0, wx.EXPAND | wx.ALL, 5)
        playerOptions.SetSizer(playerOptionsSizer)
        main_sizer.Add(playerOptions, 0, wx.EXPAND | wx.ALL, 8)

        okCancelSizer = wx.BoxSizer(wx.HORIZONTAL)
        for control in panel.GetChildren():
            if control.Name == "ok_cancel":
                okCancelSizer.Add(control, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(okCancelSizer, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(main_sizer)
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(root_sizer)
        self.Layout()
        panel.FitInside()
        changeButton.Bind(wx.EVT_BUTTON, self.onChange)
        changeCookiesButton.Bind(wx.EVT_BUTTON, self.onChangeCookies)
        clearCookiesButton.Bind(wx.EVT_BUTTON, self.onClearCookies)
        self.autoDetectItem.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoLoadItem.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoCheckForUpdates.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.debugMode.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.backgroundMonitoring.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.browserIntegration.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.repeateTracks.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.autoPlayNext.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.continueWatching.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.eqButton.Bind(wx.EVT_BUTTON, self.onEqualizer)
        self.themeBox.Bind(wx.EVT_CHOICE, self.onThemeChange)
        okButton.Bind(wx.EVT_BUTTON, self.onOk)
        apply_theme(self)
        self.ShowModal()

    def getAudioOutputDeviceSelection(self, selected_device):
        selected_device = _normalise_audio_output_device(selected_device)
        for index, device in enumerate(self.audioOutputDevices):
            if device["id"] == selected_device:
                return index
        return 0

    def onThemeChange(self, event):
        new_theme = self.theme_keys[self.themeBox.Selection]
        apply_theme(self, theme_name=new_theme)

    def onEqualizer(self, event):
        from gui.equalizer_dialog import EqualizerDialog
        from media_player.equalizer import EqualizerService

        dlg = EqualizerDialog(self, EqualizerService())
        dlg.ShowModal()
        dlg.Destroy()

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
        wildcard = _("ملفات نصية (*.txt)|*.txt")
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
        old_browser_integration = config_get("browser_integration")
        for key, item in self.preferences.items():
            config_set(key, item)
        new_browser_integration = config_get("browser_integration")
        if new_browser_integration != old_browser_integration:
            if new_browser_integration:
                success = windows_url_association.register_browser_integration()
            else:
                success = windows_url_association.unregister_browser_integration()
            if not success and sys.platform == "win32":
                config_set("browser_integration", old_browser_integration)
                wx.MessageBox(
                    _("تعذر تحديث تكامل المتصفح في Windows."),
                    _("خطأ"),
                    style=wx.ICON_ERROR,
                    parent=self,
                )
        if not self.mp3Quality.Selection == int(config_get("conversion")):
            config_set("conversion", self.mp3Quality.Selection)
        config_set(
            "defaultformat", self.formats.Selection
        ) if not self.formats.Selection == int(config_get("defaultformat")) else None
        config_set("defaultvideoquality", self.videoQuality.Selection)
        config_set("defaultaudioquality", self.audioQuality.Selection)
        config_set(
            "audiooutputdevice",
            self.audioOutputDevices[self.audioOutputDevice.Selection]["id"],
        )
        config_set("playback_speed_step", self.playbackSpeedStep.Value)
        config_set("theme", self.theme_keys[self.themeBox.Selection])
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
