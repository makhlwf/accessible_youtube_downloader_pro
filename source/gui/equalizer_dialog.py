import wx
from settings_handler import config_get, config_set
from media_player.equalizer import EqualizerService


class EqualizerDialog(wx.Dialog):
    def __init__(self, parent, equalizer_service: EqualizerService):
        super().__init__(parent, title="Equalizer Settings", size=(600, 400))
        self.equalizer_service = equalizer_service

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Presets
        preset_sizer = wx.BoxSizer(wx.HORIZONTAL)
        preset_sizer.Add(wx.StaticText(self, label="Preset:"), 0, wx.ALL | wx.CENTER, 5)
        self.preset_choice = wx.Choice(
            self, choices=["Flat", "Rock", "Pop", "Classical", "Jazz"]
        )
        self.preset_choice.SetStringSelection(str(config_get("eq_preset")))
        self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        preset_sizer.Add(self.preset_choice, 1, wx.ALL, 5)
        sizer.Add(preset_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Sliders
        bands_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sliders = {}

        # 10 bands + preamp
        # frequencies: 60, 170, 310, 600, 1k, 3k, 6k, 12k, 14k, 16k
        frequencies = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]

        # Preamp
        self.add_slider(bands_sizer, self, "Preamp", "eq_preamp", -20, 20)

        for i, freq in enumerate(frequencies):
            self.add_slider(bands_sizer, self, f"{freq}Hz", f"band_{i}", -20, 20)

        sizer.Add(bands_sizer, 1, wx.EXPAND | wx.ALL, 5)

        # Buttons
        button_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK)
        cancel_btn = wx.Button(self, wx.ID_CANCEL)
        button_sizer.AddButton(ok_btn)
        button_sizer.AddButton(cancel_btn)
        button_sizer.Realize()
        sizer.Add(button_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizer(sizer)
        self.Layout()

    def add_slider(self, sizer, parent, label, config_key, min_val, max_val):
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER)

        slider = wx.Slider(
            parent,
            value=int(config_get(config_key) or 0),
            minValue=min_val,
            maxValue=max_val,
            style=wx.SL_VERTICAL,
        )
        slider.Bind(
            wx.EVT_SLIDER, lambda event: self.on_slider_change(event, config_key)
        )
        # Manually trigger to sync initial value
        self.on_slider_change(None, config_key)

        # Accessibility
        slider.SetName(label)

        vbox.Add(slider, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(vbox, 0, wx.EXPAND | wx.ALL, 5)
        self.sliders[config_key] = slider

    def on_slider_change(self, event, config_key):
        value = event.GetInt() if event else int(config_get(config_key) or 0)
        config_set(config_key, float(value))
        config_set("eq_enabled", True)

        if config_key == "eq_preamp":
            self.equalizer_service.set_preamp(float(value))
        else:
            index = int(config_key.split("_")[1])
            self.equalizer_service.set_band(index, float(value))

        # Re-apply to trigger the change in VLC if the parent has a player
        if hasattr(self.Parent, "player") and self.Parent.player:
            self.equalizer_service.apply_to_player(self.Parent.player.media)

    def on_preset_change(self, event):
        preset = self.preset_choice.GetStringSelection()
        config_set("eq_preset", preset)
        # Apply logic for presets would go here
