import unittest
from unittest.mock import patch

import wx

from gui import equalizer_dialog
from gui.equalizer_dialog import CUSTOM_PRESET, EqualizerDialog, _preset_labels
from media_player.equalizer import EqualizerService


class FakeEqualizerService:
    def __init__(self):
        self.preamp = 0.0
        self.bands = [0.0] * 10
        self.set_preamp_called = False
        self.set_band_called = False
        self.last_preamp = 0.0
        self.last_band = (0, 0.0)
        self.applied_presets = []

    def load_settings(self):
        pass

    def set_preamp(self, val):
        self.preamp = val
        self.set_preamp_called = True
        self.last_preamp = val

    def set_band(self, idx, val):
        self.bands[idx] = val
        self.set_band_called = True
        self.last_band = (idx, val)

    def get_preamp(self):
        return self.preamp

    def get_band(self, idx):
        return self.bands[idx]

    def apply_preset(self, name):
        preset = EqualizerService.PRESETS[name]
        self.applied_presets.append(name)
        self.set_preamp(float(preset["preamp"]))
        for index, gain in enumerate(preset["bands"]):
            self.set_band(index, float(gain))

    def reset(self):
        self.set_preamp(0.0)
        for index in range(10):
            self.set_band(index, 0.0)

    def apply_to_player(self, player):
        pass

    def save_settings(self):
        pass


class TestEqualizerDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()
        self.fake_service = FakeEqualizerService()
        self.saved_config = {}
        self.config_get_patch = patch.object(
            equalizer_dialog,
            "config_get",
            lambda key: self.saved_config.get(key),
        )
        self.config_set_patch = patch.object(
            equalizer_dialog,
            "config_set",
            lambda key, value: self.saved_config.update({key: value}),
        )
        self.config_get_patch.start()
        self.config_set_patch.start()
        self.dialog = EqualizerDialog(None, self.fake_service)

    def tearDown(self):
        self.config_get_patch.stop()
        self.config_set_patch.stop()
        self.app.Destroy()

    def test_preamp_slider_change(self):
        slider = self.dialog.sliders["preamp"]
        slider.SetValue(10)

        event = wx.CommandEvent(wx.EVT_SLIDER.typeId, slider.GetId())
        event.SetInt(10)
        self.dialog.on_slider_change(event, "preamp")
        # Trigger the timer callback manually
        self.dialog.on_update_timer(None)

        assert self.fake_service.set_preamp_called is True
        assert self.fake_service.last_preamp == 10.0

    def test_band_slider_change(self):
        slider = self.dialog.sliders["band_0"]
        slider.SetValue(5)

        event = wx.CommandEvent(wx.EVT_SLIDER.typeId, slider.GetId())
        event.SetInt(5)
        self.dialog.on_slider_change(event, "band_0")
        # Trigger the timer callback manually
        self.dialog.on_update_timer(None)

        assert self.fake_service.set_band_called is True
        assert self.fake_service.last_band == (0, 5.0)

    def test_every_preset_is_offered_with_a_label(self):
        labels = _preset_labels()
        assert self.dialog.preset_keys == [
            *EqualizerService.PRESETS,
            CUSTOM_PRESET,
        ]
        for key in self.dialog.preset_keys:
            assert labels.get(key), key

    def test_choosing_a_preset_applies_and_enables_it(self):
        index = self.dialog.preset_keys.index("Bass Boost")
        self.dialog.preset_choice.Selection = index
        self.dialog.on_preset_change(None)

        assert self.fake_service.applied_presets == ["Bass Boost"]
        assert self.fake_service.get_preamp() == -3.0
        assert self.saved_config["eq_preset"] == "Bass Boost"
        assert self.saved_config["eq_enabled"] is True

    def test_moving_a_slider_switches_to_custom(self):
        self.dialog.preset_choice.Selection = self.dialog.preset_keys.index("Rock")
        self.dialog.on_preset_change(None)

        slider = self.dialog.sliders["band_0"]
        slider.SetValue(-7)
        event = wx.CommandEvent(wx.EVT_SLIDER.typeId, slider.GetId())
        event.SetInt(-7)
        self.dialog.on_slider_change(event, "band_0")

        assert self.saved_config["eq_preset"] == CUSTOM_PRESET
        assert (
            self.dialog.preset_keys[self.dialog.preset_choice.Selection]
            == CUSTOM_PRESET
        )

    def test_custom_selection_keeps_current_values(self):
        self.dialog.preset_choice.Selection = self.dialog.preset_keys.index(
            CUSTOM_PRESET
        )
        self.dialog.on_preset_change(None)

        assert self.fake_service.applied_presets == []
        assert self.saved_config["eq_preset"] == CUSTOM_PRESET

    def test_reset_returns_to_flat(self):
        self.dialog.preset_choice.Selection = self.dialog.preset_keys.index("Techno")
        self.dialog.on_preset_change(None)
        self.dialog.on_reset(None)

        assert self.fake_service.get_preamp() == 0.0
        assert self.fake_service.bands == [0.0] * 10
        assert self.saved_config["eq_preset"] == "Flat"
        assert self.saved_config["eq_enabled"] is False


if __name__ == "__main__":
    unittest.main()
