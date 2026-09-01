import os
import sys
import threading

import wx

import cookies_manager
import utils
import windows_url_association
from language_handler import _, supported_languages
from settings_handler import config_get, config_set
from sponsorblock_handler import (
    DEFAULT_API_URL,
    category_labels,
    format_categories,
    parse_categories,
)
from theme_handler import THEMES, apply_theme, apply_theme_to_all_windows

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


def _as_float(value, fallback):
    try:
        return float(value)
    except TypeError, ValueError:
        return fallback


def _normalise_api_url(value):
    url = str(value or "").strip().rstrip("/")
    if not url:
        return DEFAULT_API_URL
    if "://" not in url:
        url = f"https://{url}"
    return url


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


def _accessible_name(label):
    return str(label).replace("&", "").strip().rstrip(":：").strip()


_WX_ACCESSIBLE_BASE = getattr(wx, "Accessible", None)
if not isinstance(_WX_ACCESSIBLE_BASE, type):
    _WX_ACCESSIBLE_BASE = object


def _wx_constant(name, fallback):
    value = getattr(wx, name, fallback)
    return value if isinstance(value, int) else fallback


class ControlAccessible(_WX_ACCESSIBLE_BASE):
    def __init__(self, control):
        if _WX_ACCESSIBLE_BASE is object:
            super().__init__()
        else:
            super().__init__(control)
        self.control = control

    def GetName(self, child_id):
        label = getattr(self.control, "_accessible_label", "")
        if not label:
            get_name = getattr(self.control, "GetName", None)
            if callable(get_name):
                label = get_name()
            elif hasattr(self.control, "Name"):
                label = getattr(self.control, "Name", "")
        return _wx_constant("ACC_OK", 0), _accessible_name(label or "")


def _set_accessible_name(control, label):
    name = _accessible_name(label)
    if name:
        set_name = getattr(control, "SetName", None)
        if callable(set_name):
            set_name(name)
        control._accessible_label = name
        set_accessible = getattr(control, "SetAccessible", None)
        if callable(set_accessible) and _WX_ACCESSIBLE_BASE is not object:
            try:
                if not getattr(control, "_accessible", None):
                    control._accessible = ControlAccessible(control)
                    set_accessible(control._accessible)
            except Exception:
                control._accessible = None


class CheckBoxAccessible(_WX_ACCESSIBLE_BASE):
    def __init__(self, control):
        if _WX_ACCESSIBLE_BASE is object:
            super().__init__()
        else:
            super().__init__(control)
        self.control = control

    def GetName(self, child_id):
        label = getattr(self.control, "_accessible_label", "")
        get_label = getattr(self.control, "GetLabel", None)
        if not label and callable(get_label):
            label = get_label()
        return _wx_constant("ACC_OK", 0), _accessible_name(label)

    def GetRole(self, child_id):
        return _wx_constant("ACC_OK", 0), _wx_constant("ROLE_SYSTEM_CHECKBUTTON", 0x2C)

    def GetState(self, child_id):
        state = _wx_constant("ACC_STATE_SYSTEM_FOCUSABLE", 0x100000)
        get_value = getattr(self.control, "GetValue", None)
        if callable(get_value) and get_value():
            state |= _wx_constant("ACC_STATE_SYSTEM_CHECKED", 0x10)
        is_enabled = getattr(self.control, "IsEnabled", None)
        if callable(is_enabled) and not is_enabled():
            state |= _wx_constant("ACC_STATE_SYSTEM_UNAVAILABLE", 0x1)
        has_focus = getattr(self.control, "HasFocus", None)
        if callable(has_focus) and has_focus():
            state |= _wx_constant("ACC_STATE_SYSTEM_FOCUSED", 0x4)
        return _wx_constant("ACC_OK", 0), state


class SettingsCheckBox(wx.CheckBox):
    def __init__(self, parent, id, label, **kwargs):
        super().__init__(parent, id, label, **kwargs)
        self._accessible_label = _accessible_name(label)
        self._accessible = None
        set_accessible = getattr(self, "SetAccessible", None)
        if callable(set_accessible) and _WX_ACCESSIBLE_BASE is not object:
            try:
                self._accessible = CheckBoxAccessible(self)
                set_accessible(self._accessible)
            except Exception:
                self._accessible = None


def _add_row(sizer, label, control):
    """Place a label/control pair on a two-column grid sizer."""
    sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
    sizer.Add(control, 1, wx.EXPAND | wx.ALL, 5)


def _labelled_grid():
    grid = wx.FlexGridSizer(0, 2, 6, 8)
    grid.AddGrowableCol(1, 1)
    return grid


class SettingsDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title=_("الإعدادات"))
        self.SetMinSize((600, 520))
        self.SetSize((780, 680))
        self.Centre()
        self.preferences = {}
        self.theme_keys = list(THEMES.keys())
        self.theme_labels = _theme_labels()
        self.pages = []

        self.notebook = wx.Notebook(self, -1, name="settings_tabs")
        self._build_general_page()
        self._build_download_page()
        self._build_player_page()
        self._build_sponsorblock_page()
        self._build_cookies_page()
        self._build_advanced_page()
        okButton = wx.Button(self, wx.ID_OK, _("مواف&ق"), name="ok_cancel")
        okButton.SetDefault()
        cancelButton = wx.Button(self, wx.ID_CANCEL, _("إل&غاء"), name="ok_cancel")
        okCancelSizer = wx.BoxSizer(wx.HORIZONTAL)
        okCancelSizer.Add(okButton, 1, wx.EXPAND | wx.ALL, 5)
        okCancelSizer.Add(cancelButton, 1, wx.EXPAND | wx.ALL, 5)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 8)
        root_sizer.Add(okCancelSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(root_sizer)
        self.Layout()
        for page in self.pages:
            page.FitInside()

        self._bind_events(okButton)
        self._update_sponsorblock_controls()
        apply_theme(self)
        self.ShowModal()

    def _new_page(self, title):
        """Add a scrollable page to the notebook and return it with its sizer."""
        page = wx.ScrolledWindow(self.notebook, -1)
        page.SetScrollRate(0, 8)
        self.notebook.AddPage(page, title)
        self.pages.append(page)
        return page, wx.BoxSizer(wx.VERTICAL)

    def _build_general_page(self):
        page, sizer = self._new_page(_("عام"))
        grid = _labelled_grid()

        language_label_text = _("لغة البرنامج: ")
        language_label = wx.StaticText(page, -1, language_label_text, name="language")
        self.languageBox = wx.Choice(page, -1, name="language")
        self.languageBox.Set(list(supported_languages.keys()))
        _set_accessible_name(self.languageBox, language_label_text)
        try:
            self.languageBox.Selection = languages[config_get("lang")]
        except KeyError:
            self.languageBox.Selection = 0
        _add_row(grid, language_label, self.languageBox)

        theme_label_text = _("مظهر البرنامج: ")
        theme_label = wx.StaticText(page, -1, theme_label_text)
        self.themeBox = wx.Choice(
            page,
            -1,
            name="theme",
            choices=[self.theme_labels.get(theme, theme) for theme in self.theme_keys],
        )
        _set_accessible_name(self.themeBox, theme_label_text)
        try:
            self.themeBox.Selection = self.theme_keys.index(config_get("theme"))
        except ValueError:
            self.themeBox.Selection = 0
        _add_row(grid, theme_label, self.themeBox)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        self.autoDetectItem = SettingsCheckBox(
            page,
            -1,
            _("اكتشاف الروابط تلقائيًا عند فتح البرنامج"),
            name="autodetect",
        )
        self.autoDetectItem.SetValue(config_get("autodetect"))
        self.autoCheckForUpdates = SettingsCheckBox(
            page,
            -1,
            _("الكشف عن التحديثات الجديدة تلقائيًا عند فتح البرنامج"),
            name="checkupdates",
        )
        self.autoCheckForUpdates.SetValue(config_get("checkupdates"))
        self.autoLoadItem = SettingsCheckBox(
            page,
            -1,
            _(
                "تحميل المزيد من نتائج البحث عند الوصول إلى نهاية قائمة الفيديوهات المعروضة"
            ),
            name="autoload",
        )
        self.autoLoadItem.SetValue(config_get("autoload"))
        for checkbox in (
            self.autoDetectItem,
            self.autoCheckForUpdates,
            self.autoLoadItem,
        ):
            sizer.Add(checkbox, 0, wx.EXPAND | wx.ALL, 5)
        page.SetSizer(sizer)

    def _build_download_page(self):
        page, sizer = self._new_page(_("التنزيل"))
        grid = _labelled_grid()

        path_label_text = _("مسار مجلد التنزيل: ")
        path_label = wx.StaticText(page, -1, path_label_text)
        self.pathField = wx.TextCtrl(
            page,
            -1,
            value=config_get("path"),
            name="path",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        self.pathField.SetMinSize((-1, 56))
        _set_accessible_name(self.pathField, path_label_text)
        self.changePathButton = wx.Button(page, -1, _("&تغيير المسار"), name="path")
        path_controls = wx.BoxSizer(wx.HORIZONTAL)
        path_controls.Add(self.pathField, 1, wx.EXPAND | wx.RIGHT, 5)
        path_controls.Add(self.changePathButton, 0, wx.EXPAND)
        _add_row(grid, path_label, path_controls)

        format_label_text = _("صيغة التحميل المباشر: ")
        format_label = wx.StaticText(page, -1, format_label_text)
        self.formats = wx.Choice(
            page,
            -1,
            choices=[
                _("فيديو (mp4)"),
                _("فيديو (mkv)"),
                _("صوت (m4a)"),
                _("صوت (mp3)"),
                _("صوت (wav)"),
                _("صوت (flac)"),
            ],
        )
        _set_accessible_name(self.formats, format_label_text)
        default_format = int(config_get("defaultformat"))
        if not (0 <= default_format < 6):
            default_format = 0
        self.formats.Selection = default_format
        _add_row(grid, format_label, self.formats)
        conversion_label_text = _("جودة الصوت: ")
        conversion_label = wx.StaticText(page, -1, conversion_label_text)
        self.audioQuality2 = wx.Choice(
            page,
            -1,
            choices=[_("96 ك.ب/ث"), _("128 ك.ب/ث"), _("192 ك.ب/ث"), _("320 ك.ب/ث")],
            name="conversion",
        )
        _set_accessible_name(self.audioQuality2, conversion_label_text)
        self.audioQuality2.Selection = int(config_get("conversion"))
        _add_row(grid, conversion_label, self.audioQuality2)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        page.SetSizer(sizer)

    def _build_player_page(self):
        page, sizer = self._new_page(_("المشغل"))
        grid = _labelled_grid()

        video_quality_label_text = _("جودة الفيديو الافتراضية: ")
        self.videoQualityLabel = wx.StaticText(page, -1, video_quality_label_text)
        self.videoQuality = wx.Choice(
            page,
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
        _set_accessible_name(self.videoQuality, video_quality_label_text)
        self.videoQuality.Selection = int(config_get("defaultvideoquality"))
        _add_row(grid, self.videoQualityLabel, self.videoQuality)

        audio_quality_label_text = _("جودة الصوت الافتراضية: ")
        self.audioQualityLabel = wx.StaticText(page, -1, audio_quality_label_text)
        self.audioQuality = wx.Choice(
            page,
            -1,
            choices=[_("منخفضة"), _("متوسطة"), _("عالية")],
        )
        _set_accessible_name(self.audioQuality, audio_quality_label_text)
        self.audioQuality.Selection = int(config_get("defaultaudioquality"))
        _add_row(grid, self.audioQualityLabel, self.audioQuality)

        self.audioOutputDevices = _get_audio_output_device_choices()
        audio_output_label_text = _("جهاز إخراج الصوت: ")
        self.audioOutputDeviceLabel = wx.StaticText(page, -1, audio_output_label_text)
        self.audioOutputDevice = wx.Choice(
            page,
            -1,
            choices=[device["description"] for device in self.audioOutputDevices],
        )
        _set_accessible_name(self.audioOutputDevice, audio_output_label_text)
        self.audioOutputDevice.Selection = self.getAudioOutputDeviceSelection(
            config_get("audiooutputdevice")
        )
        _add_row(grid, self.audioOutputDeviceLabel, self.audioOutputDevice)
        playback_speed_label_text = _("مقدار تغيير سرعة التشغيل: ")
        self.playbackSpeedStepLabel = wx.StaticText(page, -1, playback_speed_label_text)
        self.playbackSpeedStep = wx.SpinCtrlDouble(
            page,
            -1,
            value=str(config_get("playback_speed_step")),
            min=0.01,
            max=1.0,
            inc=0.01,
        )
        _set_accessible_name(self.playbackSpeedStep, playback_speed_label_text)
        _add_row(grid, self.playbackSpeedStepLabel, self.playbackSpeedStep)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        self.continueWatching = SettingsCheckBox(
            page,
            -1,
            _("متابعة المشاهدة بعد إغلاق الفيديو وتشغيله من جديد"),
            name="continue",
        )
        self.continueWatching.SetValue(config_get("continue"))
        self.openPlayerFullscreen = SettingsCheckBox(
            page,
            -1,
            _("فتح مشغل الوسائط في وضع ملء الشاشة افتراضيًا"),
            name="player_fullscreen_default",
        )
        self.openPlayerFullscreen.SetValue(config_get("player_fullscreen_default"))
        self.repeateTracks = SettingsCheckBox(
            page,
            -1,
            _("إعادة تشغيل المقطع تلقائيًا عند انتهائه"),
            name="repeatTracks",
        )
        self.repeateTracks.SetValue(config_get("repeatTracks"))
        self.autoPlayNext = SettingsCheckBox(
            page,
            -1,
            _("الانتقال إلى المقطع التالي تلقائيًا عند انتهاء المقطع الحالي"),
            name="autonext",
        )
        self.autoPlayNext.SetValue(config_get("autonext"))
        for checkbox in (
            self.continueWatching,
            self.openPlayerFullscreen,
            self.repeateTracks,
            self.autoPlayNext,
        ):
            sizer.Add(checkbox, 0, wx.EXPAND | wx.ALL, 5)

        self.eqButton = wx.Button(page, -1, _("إعدادات المعادل..."))
        sizer.Add(self.eqButton, 0, wx.EXPAND | wx.ALL, 5)
        page.SetSizer(sizer)

    def _build_sponsorblock_page(self):
        page, sizer = self._new_page("SponsorBlock")
        self.sponsorBlock = SettingsCheckBox(
            page,
            -1,
            _("تفعيل SponsorBlock لتخطي المقاطع الدعائية تلقائيًا"),
            name="sponsorblock",
        )
        self.sponsorBlock.SetValue(bool(config_get("sponsorblock")))
        sizer.Add(self.sponsorBlock, 0, wx.EXPAND | wx.ALL, 5)
        self.sponsorBlockNotify = SettingsCheckBox(
            page,
            -1,
            _("الإعلان عن كل مقطع يتم تخطيه"),
            name="sponsorblock_notify",
        )
        self.sponsorBlockNotify.SetValue(bool(config_get("sponsorblock_notify")))
        sizer.Add(self.sponsorBlockNotify, 0, wx.EXPAND | wx.ALL, 5)

        self.sponsorBlockCategoriesLabel = wx.StaticText(
            page, -1, _("الفئات التي يتم تخطيها:")
        )
        sizer.Add(self.sponsorBlockCategoriesLabel, 0, wx.EXPAND | wx.ALL, 5)
        enabled_categories = parse_categories(config_get("sponsorblock_categories"))
        self.sponsorBlockCategories = {}
        categories_grid = wx.FlexGridSizer(0, 2, 4, 8)
        categories_grid.AddGrowableCol(0, 1)
        categories_grid.AddGrowableCol(1, 1)
        for category, label in category_labels().items():
            categoryBox = SettingsCheckBox(
                page, -1, label, name=f"sponsorblock_category_{category}"
            )
            categoryBox.SetValue(category in enabled_categories)
            self.sponsorBlockCategories[category] = categoryBox
            categories_grid.Add(categoryBox, 0, wx.EXPAND | wx.ALL, 3)
        sizer.Add(categories_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        grid = _labelled_grid()
        min_duration_label_text = _("تجاهل المقاطع الأقصر من (بالثواني): ")
        self.sponsorBlockMinDurationLabel = wx.StaticText(
            page, -1, min_duration_label_text
        )
        self.sponsorBlockMinDuration = wx.SpinCtrlDouble(
            page,
            -1,
            value=str(_as_float(config_get("sponsorblock_min_duration"), 0.0)),
            min=0.0,
            max=60.0,
            inc=0.5,
        )
        _set_accessible_name(self.sponsorBlockMinDuration, min_duration_label_text)
        _add_row(grid, self.sponsorBlockMinDurationLabel, self.sponsorBlockMinDuration)

        api_url_label_text = _("عنوان خادم SponsorBlock: ")
        self.sponsorBlockApiUrlLabel = wx.StaticText(page, -1, api_url_label_text)
        self.sponsorBlockApiUrl = wx.TextCtrl(
            page,
            -1,
            value=_normalise_api_url(config_get("sponsorblock_api_url")),
            name="sponsorblock_api_url",
        )
        _set_accessible_name(self.sponsorBlockApiUrl, api_url_label_text)
        _add_row(grid, self.sponsorBlockApiUrlLabel, self.sponsorBlockApiUrl)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 5)
        page.SetSizer(sizer)

    def _build_cookies_page(self):
        page, sizer = self._new_page(_("الكوكيز"))
        grid = _labelled_grid()

        browser_label_text = _("المتصفح لاستيراد الكوكيز: ")
        browser_label = wx.StaticText(page, -1, browser_label_text)
        self.installed_browsers = cookies_manager.get_installed_browsers()
        self.browserChoice = wx.Choice(
            page,
            -1,
            name="browser_cookies_source",
            choices=[b["name"] for b in self.installed_browsers],
        )
        _set_accessible_name(self.browserChoice, browser_label_text)
        saved_browser_source = config_get("browser_cookies_source")
        selected_browser_idx = 0
        for idx, b in enumerate(self.installed_browsers):
            if b["id"] == saved_browser_source or b["name"] == saved_browser_source:
                selected_browser_idx = idx
                break
        self.browserChoice.Selection = selected_browser_idx
        self.importBrowserCookiesButton = wx.Button(
            page, -1, _("استيراد من المتصفح"), name="cookies"
        )
        browser_controls = wx.BoxSizer(wx.HORIZONTAL)
        browser_controls.Add(self.browserChoice, 1, wx.EXPAND | wx.RIGHT, 5)
        browser_controls.Add(self.importBrowserCookiesButton, 0, wx.EXPAND)
        _add_row(grid, browser_label, browser_controls)

        cookies_label_text = _("مسار ملف الكوكيز: ")
        cookies_label = wx.StaticText(page, -1, cookies_label_text)
        self.cookiesPathField = wx.TextCtrl(
            page,
            -1,
            value=config_get("cookiespath"),
            name="cookies",
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        self.cookiesPathField.SetMinSize((-1, 56))
        _set_accessible_name(self.cookiesPathField, cookies_label_text)
        self.changeCookiesButton = wx.Button(page, -1, _("تغيير"), name="cookies")
        self.clearCookiesButton = wx.Button(page, -1, _("حذف"), name="cookies")
        cookies_controls = wx.BoxSizer(wx.HORIZONTAL)
        cookies_controls.Add(self.cookiesPathField, 1, wx.EXPAND | wx.RIGHT, 5)
        cookies_controls.Add(self.changeCookiesButton, 0, wx.EXPAND | wx.RIGHT, 5)
        cookies_controls.Add(self.clearCookiesButton, 0, wx.EXPAND)
        _add_row(grid, cookies_label, cookies_controls)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)
        page.SetSizer(sizer)

    def _build_advanced_page(self):
        page, sizer = self._new_page(_("متقدم"))
        grid = _labelled_grid()

        self.player_client_choices = utils.get_player_client_choices()
        player_client_label_text = _("عميل مشغل يوتيوب: ")
        self.playerClientLabel = wx.StaticText(page, -1, player_client_label_text)
        self.playerClientBox = wx.Choice(
            page,
            -1,
            choices=[label for _, label in self.player_client_choices],
            name="player_client",
        )
        _set_accessible_name(self.playerClientBox, player_client_label_text)
        self.playerClientBox.Selection = self.getPlayerClientSelection(
            config_get("player_client")
        )
        _add_row(grid, self.playerClientLabel, self.playerClientBox)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        self.backgroundMonitoring = SettingsCheckBox(
            page,
            -1,
            _("التشغيل في الخلفية ومراقبة الحافظة عند بدء تشغيل النظام"),
            name="background_monitoring",
        )
        self.backgroundMonitoring.SetValue(config_get("background_monitoring"))
        self.browserIntegration = SettingsCheckBox(
            page,
            -1,
            _("تفعيل التكامل الآمن مع إضافة المتصفح"),
            name="browser_integration",
        )
        self.browserIntegration.SetValue(config_get("browser_integration"))
        if sys.platform != "win32":
            self.browserIntegration.Disable()
        self.debugMode = SettingsCheckBox(
            page,
            -1,
            _("تفعيل رسائل تصحيح الأخطاء للمطورين فقط"),
            name="debug",
        )
        self.debugMode.SetValue(config_get("debug"))
        for checkbox in (
            self.backgroundMonitoring,
            self.browserIntegration,
            self.debugMode,
        ):
            sizer.Add(checkbox, 0, wx.EXPAND | wx.ALL, 5)
        page.SetSizer(sizer)

    def _bind_events(self, okButton):
        self.changePathButton.Bind(wx.EVT_BUTTON, self.onChange)
        self.changeCookiesButton.Bind(wx.EVT_BUTTON, self.onChangeCookies)
        self.clearCookiesButton.Bind(wx.EVT_BUTTON, self.onClearCookies)
        self.importBrowserCookiesButton.Bind(wx.EVT_BUTTON, self.onImportBrowserCookies)
        for checkbox in (
            self.autoDetectItem,
            self.autoLoadItem,
            self.autoCheckForUpdates,
            self.debugMode,
            self.backgroundMonitoring,
            self.browserIntegration,
            self.repeateTracks,
            self.autoPlayNext,
            self.sponsorBlockNotify,
            self.continueWatching,
            self.openPlayerFullscreen,
        ):
            checkbox.Bind(wx.EVT_CHECKBOX, self.onCheck)
        self.sponsorBlock.Bind(wx.EVT_CHECKBOX, self.onSponsorBlockToggle)
        self.eqButton.Bind(wx.EVT_BUTTON, self.onEqualizer)
        self.themeBox.Bind(wx.EVT_CHOICE, self.onThemeChange)
        okButton.Bind(wx.EVT_BUTTON, self.onOk)

    def getPlayerClientSelection(self, selected_client):
        for index, (client_id, _label) in enumerate(self.player_client_choices):
            if client_id == selected_client:
                return index
        return 0

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

    def onSponsorBlockToggle(self, event):
        self.onCheck(event)
        self._update_sponsorblock_controls()

    def _update_sponsorblock_controls(self):
        """Grey out the SponsorBlock details while the feature itself is off."""
        enabled = self._checkbox_value(self.sponsorBlock)
        controls = [
            self.sponsorBlockNotify,
            self.sponsorBlockCategoriesLabel,
            self.sponsorBlockMinDurationLabel,
            self.sponsorBlockMinDuration,
            self.sponsorBlockApiUrlLabel,
            self.sponsorBlockApiUrl,
            *self.sponsorBlockCategories.values(),
        ]
        for control in controls:
            control.Enable(enabled)

    def _selected_sponsorblock_categories(self):
        return [
            category
            for category, control in self.sponsorBlockCategories.items()
            if self._checkbox_value(control)
        ]

    def _save_sponsorblock_settings(self):
        if not hasattr(self, "sponsorBlockCategories"):
            return
        config_set(
            "sponsorblock_categories",
            format_categories(self._selected_sponsorblock_categories()),
        )
        config_set(
            "sponsorblock_min_duration",
            _as_float(
                self.sponsorBlockMinDuration.GetValue()
                if hasattr(self.sponsorBlockMinDuration, "GetValue")
                else getattr(self.sponsorBlockMinDuration, "Value", 0.0),
                0.0,
            ),
        )
        config_set(
            "sponsorblock_api_url",
            _normalise_api_url(
                self.sponsorBlockApiUrl.GetValue()
                if hasattr(self.sponsorBlockApiUrl, "GetValue")
                else getattr(self.sponsorBlockApiUrl, "Value", "")
            ),
        )

    def onCheck(self, event):
        obj = event.EventObject
        if obj is self.repeateTracks and self._checkbox_value(self.repeateTracks):
            self.autoPlayNext.SetValue(False)
            self._queue_checkbox_preference(self.autoPlayNext)
        elif obj is self.autoPlayNext and self._checkbox_value(self.autoPlayNext):
            self.repeateTracks.SetValue(False)
            self._queue_checkbox_preference(self.repeateTracks)
        self._queue_checkbox_preference(obj)

    def _checkbox_value(self, control):
        if hasattr(control, "GetValue"):
            return control.GetValue()
        return control.Value

    def _queue_checkbox_preference(self, control):
        value = self._checkbox_value(control)
        if control.Name in self.preferences and config_get(control.Name) == value:
            del self.preferences[control.Name]
        elif value != config_get(control.Name):
            self.preferences[control.Name] = value

    def onChange(self, event):
        new = wx.DirSelector(
            _("اختر مجلد التنزيل"),
            os.path.join(os.getenv("userprofile"), "downloads"),
            parent=self,
        )
        if new != "":
            self.preferences["path"] = new
            self.pathField.Value = new
            self.pathField.SetFocus()

    def validate_cookies_path(self, path):
        if not path:
            return True
        if not os.path.exists(path):
            wx.MessageBox(
                _("ملف الكوكيز المختار غير موجود."),
                _("تنبيه"),
                style=wx.OK | wx.ICON_WARNING,
                parent=self,
            )
            return False
        return True

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
            if not self.validate_cookies_path(path):
                dlg.Destroy()
                return
            self.preferences["cookiespath"] = path
            self.cookiesPathField.Value = path
            self.cookiesPathField.SetFocus()
        dlg.Destroy()

    def onClearCookies(self, event):
        self.preferences["cookiespath"] = ""
        self.cookiesPathField.Value = ""

    def onImportBrowserCookies(self, event=None):
        if (
            hasattr(self, "importBrowserCookiesButton")
            and not self.importBrowserCookiesButton.IsEnabled()
        ):
            return
        sel = self.browserChoice.Selection
        if sel < 0 or sel >= len(self.installed_browsers):
            return
        browser_id = self.installed_browsers[sel]["id"]

        if (
            hasattr(self, "importBrowserCookiesButton")
            and self.importBrowserCookiesButton.HasFocus()
            and hasattr(self, "browserChoice")
        ):
            self.browserChoice.SetFocus()

        if hasattr(self, "importBrowserCookiesButton"):
            self.importBrowserCookiesButton.Disable()

        def _worker():
            result = cookies_manager.extract_and_save_browser_cookies(browser_id)
            wx.CallAfter(self._on_browser_cookies_imported, result, browser_id)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_browser_cookies_imported(self, result, browser_id):
        if hasattr(self, "importBrowserCookiesButton"):
            self.importBrowserCookiesButton.Enable()
        browser_name = result.get("browser") or browser_id
        if result.get("success"):
            path = result.get("path", "")
            self.cookiesPathField.Value = path
            self.preferences["cookiespath"] = path
            self.preferences["browser_cookies_source"] = browser_id
            config_set("cookiespath", path)
            config_set("browser_cookies_source", browser_id)
            try:
                import native_messaging_host

                native_messaging_host.send_ipc_message("cookies_updated", path)
            except Exception:
                pass
            count = result.get("count", 0)
            is_auth = result.get("is_authenticated", True)
            if is_auth:
                msg = _(
                    "تم استيراد {count} من الكوكيز بنجاح من متصفح {browser}."
                ).format(count=count, browser=browser_name)
            else:
                msg = _(
                    "تم استيراد {count} من الكوكيز من متصفح {browser}، ولكن يبدو أنه لم يتم العثور على جلسة تسجيل دخول نشطة لحساب يوتيوب."
                ).format(count=count, browser=browser_name)
            wx.MessageBox(
                msg,
                _("نجاح"),
                style=wx.OK | wx.ICON_INFORMATION,
                parent=self,
            )
        else:
            error_type = result.get("error_type", "unknown")
            if error_type == "locked":
                msg = _(
                    "متصفح {browser} مفتوح حاليًا. يرجى إغلاق المتصفح وإعادة المحاولة."
                ).format(browser=browser_name)
                caption = _("المتصفح مفتوح")
            elif error_type == "decrypt_failed":
                msg = _(
                    "تعذر فك تشفير كوكيز متصفح {browser} مباشرة بسبب نظام الحماية (App-Bound Encryption). يمكنك استيراد الكوكيز بضغطة واحدة من خلال إضافة البرنامج للمتصفح (HexPlayer Link Helper) أو باستخدام متصفح Firefox."
                ).format(browser=browser_name)
                caption = _("خطأ في فك التشفير")
            elif error_type == "no_cookies":
                msg = _("لم يتم العثور على كوكيز في متصفح {browser}.").format(
                    browser=browser_name
                )
                caption = _("لا توجد كوكيز")
            else:
                msg = _("فشل استيراد الكوكيز من متصفح {browser}: {error}").format(
                    browser=browser_name, error=result.get("error", "")
                )
                caption = _("خطأ")
            wx.MessageBox(
                msg,
                caption,
                style=wx.OK | wx.ICON_ERROR,
                parent=self,
            )

    def onOk(self, event):
        if hasattr(self, "browserChoice") and self.installed_browsers:
            sel = self.browserChoice.Selection
            if 0 <= sel < len(self.installed_browsers):
                self.preferences["browser_cookies_source"] = self.installed_browsers[
                    sel
                ]["id"]
        cookies_path = (
            self.cookiesPathField.Value
            if hasattr(self, "cookiesPathField")
            else self.preferences.get("cookiespath", "")
        )
        if not self.validate_cookies_path(cookies_path):
            return
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
        if self.audioQuality2.Selection != int(config_get("conversion")):
            config_set("conversion", self.audioQuality2.Selection)
        if self.formats.Selection != int(config_get("defaultformat")):
            config_set("defaultformat", str(self.formats.Selection))
        config_set("defaultvideoquality", self.videoQuality.Selection)
        config_set("defaultaudioquality", self.audioQuality.Selection)
        if hasattr(self, "playerClientBox") and hasattr(self, "player_client_choices"):
            config_set(
                "player_client",
                self.player_client_choices[self.playerClientBox.Selection][0],
            )
        config_set(
            "audiooutputdevice",
            self.audioOutputDevices[self.audioOutputDevice.Selection]["id"],
        )
        config_set(
            "playback_speed_step",
            self.playbackSpeedStep.GetValue()
            if hasattr(self.playbackSpeedStep, "GetValue")
            else getattr(self.playbackSpeedStep, "Value", 0.05),
        )
        self._save_sponsorblock_settings()
        selected_theme = self.theme_keys[self.themeBox.Selection]
        config_set("theme", selected_theme)
        apply_theme_to_all_windows(selected_theme)
        lang = {value: key for key, value in languages.items()}
        if lang[self.languageBox.Selection] != config_get("lang"):
            config_set("lang", lang[self.languageBox.Selection])
            selected_lang_str = (
                self.languageBox.GetStringSelection()
                if hasattr(self.languageBox, "GetStringSelection")
                else getattr(self.languageBox, "StringSelection", "")
            )
            msg = wx.MessageBox(
                _(
                    "لقد قمت بتغيير لغة البرنامج إلى {}, مما يعني أنه ينبغي عليك إعادة تشغيل البرنامج لتطبيق التعديلات. هل تريد القيام بذلك حالًا?"
                ).format(selected_lang_str),
                _("تنبيه"),
                style=wx.YES_NO,
                parent=self,
            )
            os.execl(sys.executable, sys.executable, *sys.argv) if msg == 2 else None
        self.Destroy()
