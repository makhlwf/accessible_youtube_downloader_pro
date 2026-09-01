import wx

from language_handler import _
from media_player.equalizer import EqualizerService
from media_player.media_gui import MediaGui
from settings_handler import config_get, config_set
from theme_handler import apply_theme

CUSTOM_PRESET = "Custom"


def _preset_labels():
    """Translated labels for every preset key, in dropdown order."""
    return {
        "Flat": _("مستو"),
        "Rock": _("روك"),
        "Pop": _("بوب"),
        "Classical": _("كلاسيكي"),
        "Jazz": _("جاز"),
        "Acoustic": _("أكوستيك"),
        "Blues": _("بلوز"),
        "Club": _("نادي ليلي"),
        "Country": _("ريفي"),
        "Dance": _("رقص"),
        "Electronic": _("إلكتروني"),
        "Hip Hop": _("هيب هوب"),
        "Large Hall": _("قاعة كبيرة"),
        "Latin": _("لاتيني"),
        "Live": _("حفل مباشر"),
        "Metal": _("ميتال"),
        "Party": _("حفلة"),
        "Piano": _("بيانو"),
        "R&B": _("آر أند بي"),
        "Reggae": _("ريغي"),
        "Ska": _("سكا"),
        "Soft Rock": _("روك هادئ"),
        "Techno": _("تكنو"),
        "Bass Boost": _("تعزيز الجهير"),
        "Bass Reducer": _("تقليل الجهير"),
        "Treble Boost": _("تعزيز الترددات العالية"),
        "Treble Reducer": _("تقليل الترددات العالية"),
        "Full Bass": _("جهير كامل"),
        "Full Treble": _("ترددات عالية كاملة"),
        "Full Bass & Treble": _("جهير وترددات عالية"),
        "Loudness": _("جهارة الصوت"),
        "Soft": _("ناعم"),
        "Deep": _("عميق"),
        "Vocal Boost": _("تعزيز الأصوات"),
        "Speech": _("كلام وبودكاست"),
        "Quran": _("قرآن وتلاوة"),
        "Audiobook": _("كتاب صوتي"),
        "Movie": _("أفلام"),
        "Gaming": _("ألعاب"),
        "Night": _("وضع ليلي"),
        "Headphones": _("سماعات رأس"),
        "Earbuds": _("سماعات أذن"),
        "Small Speakers": _("مكبرات صوت صغيرة"),
        "Car": _("سيارة"),
        CUSTOM_PRESET: _("مخصص"),
    }


class EqualizerDialog(wx.Dialog):
    def __init__(self, parent, equalizer_service: EqualizerService):
        super().__init__(parent, title=_("إعدادات المعادل"), size=(640, 480))
        self.equalizer_service = equalizer_service
        self.equalizer_service.load_settings()
        self.preset_labels = _preset_labels()
        self.preset_keys = [*EqualizerService.PRESETS, CUSTOM_PRESET]

        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_update_timer, self.update_timer)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Presets
        preset_sizer = wx.BoxSizer(wx.HORIZONTAL)
        preset_label_text = _("الإعداد المسبق:")
        preset_sizer.Add(
            wx.StaticText(self, label=preset_label_text),
            0,
            wx.ALL | wx.CENTER,
            5,
        )
        self.preset_choice = wx.Choice(
            self, choices=[self.preset_labels.get(key, key) for key in self.preset_keys]
        )
        self.preset_choice.SetName(preset_label_text.rstrip(":"))
        self.preset_choice.Selection = self.preset_keys.index(
            self._current_preset_key()
        )
        self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        preset_sizer.Add(self.preset_choice, 1, wx.ALL, 5)

        reset_btn = wx.Button(self, label=_("إعادة ضبط"))
        reset_btn.Bind(wx.EVT_BUTTON, self.on_reset)
        preset_sizer.Add(reset_btn, 0, wx.ALL, 5)

        sizer.Add(preset_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Sliders
        bands_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sliders = {}

        # 10 bands + preamp
        # frequencies: 60, 170, 310, 600, 1k, 3k, 6k, 12k, 14k, 16k
        frequencies = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]

        # Preamp
        self.add_slider(bands_sizer, self, _("مضخم الصوت"), "preamp", -20, 20)

        for i, freq in enumerate(frequencies):
            self.add_slider(bands_sizer, self, f"{freq}Hz", f"band_{i}", -20, 20)

        sizer.Add(bands_sizer, 1, wx.EXPAND | wx.ALL, 5)

        # Buttons
        button_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        button_sizer.AddButton(ok_btn)
        button_sizer.Realize()
        sizer.Add(button_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizer(sizer)
        self.Layout()
        apply_theme(self)

    def _preset_matches_current(self, key):
        preset = EqualizerService.PRESETS.get(key)
        if not preset:
            return False
        if (
            abs(float(preset["preamp"]) - float(self.equalizer_service.get_preamp()))
            > 0.01
        ):
            return False
        return all(
            abs(float(gain) - float(self.equalizer_service.get_band(index))) <= 0.01
            for index, gain in enumerate(preset["bands"])
        )

    def _current_preset_key(self):
        """Pick the dropdown entry matching the values currently in the service."""
        saved = config_get("eq_preset")
        if saved in EqualizerService.PRESETS and self._preset_matches_current(saved):
            return saved
        for key in EqualizerService.PRESETS:
            if self._preset_matches_current(key):
                return key
        return CUSTOM_PRESET

    def _select_preset_key(self, key):
        if key in self.preset_keys:
            self.preset_choice.Selection = self.preset_keys.index(key)

    def add_slider(self, sizer, parent, label, slider_id, min_val, max_val):
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER)

        if slider_id == "preamp":
            initial_value = self.equalizer_service.get_preamp()
        else:
            index = int(slider_id.split("_")[1])
            initial_value = self.equalizer_service.get_band(index)

        slider = wx.Slider(
            parent,
            value=int(initial_value),
            minValue=min_val,
            maxValue=max_val,
            style=wx.SL_VERTICAL,
        )
        slider.Bind(
            wx.EVT_SLIDER, lambda event: self.on_slider_change(event, slider_id)
        )

        # Accessibility
        slider.SetName(label)

        vbox.Add(slider, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(vbox, 0, wx.EXPAND | wx.ALL, 5)
        self.sliders[slider_id] = slider

    def on_slider_change(self, event, slider_id):
        value = event.GetInt()
        config_set("eq_enabled", True)

        if slider_id == "preamp":
            self.equalizer_service.set_preamp(float(value))
        else:
            index = int(slider_id.split("_")[1])
            self.equalizer_service.set_band(index, float(value))

        # Moving a slider by hand no longer matches the chosen preset.
        preset = self._current_preset_key()
        config_set("eq_preset", preset)
        self._select_preset_key(preset)

        # Start/Restart the debounce timer
        self.update_timer.Start(100, oneShot=True)

    def on_update_timer(self, event):
        self.equalizer_service.save_settings()
        self.apply_to_player()

    def apply_to_player(self):
        # Re-apply to trigger the change in MPV.
        if hasattr(self.Parent, "player") and self.Parent.player:
            self.equalizer_service.apply_to_player(self.Parent.player.media)
        else:
            # Fallback if dialog is opened from Settings (which doesn't have a player)
            for window in wx.GetTopLevelWindows():
                if isinstance(window, MediaGui) and window.player:
                    self.equalizer_service.apply_to_player(window.player.media)
                    break

    def on_preset_change(self, event):
        preset = self.preset_keys[self.preset_choice.Selection]
        config_set("eq_preset", preset)
        if preset == CUSTOM_PRESET:
            # "Custom" only labels the current sliders, there is nothing to apply.
            return
        config_set("eq_enabled", True)
        self.equalizer_service.apply_preset(preset)
        self.update_ui_from_service()
        self.on_update_timer(None)

    def on_reset(self, event):
        self.equalizer_service.reset()
        self.preset_choice.Selection = self.preset_keys.index("Flat")
        config_set("eq_preset", "Flat")
        config_set("eq_enabled", False)
        self.update_ui_from_service()
        self.on_update_timer(None)

    def update_ui_from_service(self):
        self.sliders["preamp"].SetValue(int(self.equalizer_service.get_preamp()))
        for i in range(10):
            slider_id = f"band_{i}"
            if slider_id in self.sliders:
                self.sliders[slider_id].SetValue(
                    int(self.equalizer_service.get_band(i))
                )
