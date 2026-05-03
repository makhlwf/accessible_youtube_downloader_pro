import unittest
from unittest.mock import MagicMock
import wx
from source.gui.equalizer_dialog import EqualizerDialog
from source.media_player.equalizer import EqualizerService


class TestEqualizerDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()
        self.mock_service = MagicMock(spec=EqualizerService)
        self.dialog = EqualizerDialog(None, self.mock_service)

    def tearDown(self):
        self.app.Destroy()

    def test_preamp_slider_change(self):
        # Trigger slider change for preamp
        # In EqualizerDialog, config_key for preamp is 'eq_preamp'
        slider = self.dialog.sliders["eq_preamp"]
        slider.SetValue(10)

        event = wx.CommandEvent(wx.EVT_SLIDER.typeId, slider.GetId())
        event.SetInt(10)
        self.dialog.on_slider_change(event, "eq_preamp")

        self.mock_service.set_preamp.assert_called_with(10.0)

    def test_band_slider_change(self):
        # Trigger slider change for band 0 (60Hz)
        slider = self.dialog.sliders["band_0"]
        slider.SetValue(5)

        event = wx.CommandEvent(wx.EVT_SLIDER.typeId, slider.GetId())
        event.SetInt(5)
        self.dialog.on_slider_change(event, "band_0")

        self.mock_service.set_band.assert_called_with(0, 5.0)


if __name__ == "__main__":
    unittest.main()
