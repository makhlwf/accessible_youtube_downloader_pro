import unittest
import wx
from gui.equalizer_dialog import EqualizerDialog


class FakeEqualizerService:
    def __init__(self):
        self.preamp = 0.0
        self.bands = [0.0] * 10
        self.set_preamp_called = False
        self.set_band_called = False
        self.last_preamp = 0.0
        self.last_band = (0, 0.0)


class FakeEqualizerService:
    def __init__(self):
        self.preamp = 0.0
        self.bands = [0.0] * 10
        self.set_preamp_called = False
        self.set_band_called = False
        self.last_preamp = 0.0
        self.last_band = (0, 0.0)

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

    def apply_to_player(self, player):
        pass

    def save_settings(self):
        pass


class TestEqualizerDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App()
        self.fake_service = FakeEqualizerService()
        self.dialog = EqualizerDialog(None, self.fake_service)

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()
