import wx
from settings_handler import config_get, config_set
from media_player.equalizer import EqualizerService
from media_player.media_gui import MediaGui
from theme_handler import apply_theme


class EqualizerDialog(wx.Dialog):
    def __init__(self, parent, equalizer_service: EqualizerService):
        super().__init__(parent, title="Equalizer Settings", size=(600, 450))
        self.equalizer_service = equalizer_service
        self.equalizer_service.load_settings()

        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_update_timer, self.update_timer)

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Presets
        preset_sizer = wx.BoxSizer(wx.HORIZONTAL)
        preset_sizer.Add(wx.StaticText(self, label="Preset:"), 0, wx.ALL | wx.CENTER, 5)
        self.preset_choice = wx.Choice(
            self, choices=["Flat", "Rock", "Pop", "Classical", "Jazz"]
        )
        current_preset = config_get("eq_preset") or "Flat"
        if current_preset not in self.preset_choice.GetStrings():
            current_preset = "Flat"
        self.preset_choice.SetStringSelection(current_preset)
        self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        preset_sizer.Add(self.preset_choice, 1, wx.ALL, 5)

        reset_btn = wx.Button(self, label="Reset")
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
        self.add_slider(bands_sizer, self, "Preamp", "preamp", -20, 20)

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
        preset = self.preset_choice.GetStringSelection()
        config_set("eq_preset", preset)
        self.equalizer_service.apply_preset(preset)
        self.update_ui_from_service()
        self.on_update_timer(None)

    def on_reset(self, event):
        self.equalizer_service.reset()
        self.preset_choice.SetStringSelection("Flat")
        config_set("eq_preset", "Flat")
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
