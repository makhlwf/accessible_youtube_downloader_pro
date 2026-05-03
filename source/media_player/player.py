import vlc
import wx
from utils import time_formatting
from threading import Thread
from settings_handler import config_get
from media_player.equalizer import EqualizerService


class Player:
    def __init__(self, filename, hwnd, window=None, options=None):
        self.instance = vlc.Instance()
        self.media = self.instance.media_player_new()
        if config_get("eq_enabled"):
            self.eq = EqualizerService()
            preamp = float(config_get("eq_preamp") or 0.0)
            self.eq.set_preamp(preamp)
            bands_raw = config_get("eq_bands")
            if isinstance(bands_raw, str):
                try:
                    bands = [float(x) for x in bands_raw.split(",")]
                except ValueError:
                    bands = []
            else:
                bands = bands_raw or []
            for i, val in enumerate(bands):
                if i < 10:
                    self.eq.set_band(i, float(val))
            self.eq.apply_to_player(self.media)
            # Enable the equalizer explicitly
            self.media.set_equalizer(self.eq.equalizer)
        self.do_reset = False
        self.window = window
        self.filename = filename
        self.hwnd = hwnd
        self.set_media(self.filename, options)
        self.media.set_hwnd(self.hwnd or 0)
        self.manager = self.media.event_manager()
        self.manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.onEnd)
        self.media.play()
        self.volume = int(config_get("volume"))
        self.media.audio_set_volume(self.volume)

    def onEnd(self, event):
        if event.type == vlc.EventType.MediaPlayerEndReached:
            self.do_reset = True
            Thread(target=self.reset).start()

    def seek(self, seconds):
        length = self.media.get_length()
        if length == -1:
            return 0.03
        try:
            return seconds / (self.media.get_length() / 1000)
        except ZeroDivisionError:
            return 0.03

    def get_duration(self):
        duration = self.media.get_length()
        if duration == -1 or not isinstance(duration, int):
            return ""
        return time_formatting(duration // 1000)

    def get_elapsed(self):
        elapsed = self.media.get_time()
        if elapsed == -1 or not isinstance(elapsed, int):
            return ""
        return time_formatting(elapsed // 1000)

    def get_remaining(self):
        length = self.media.get_length()
        time = self.media.get_time()
        if length == -1 or time == -1:
            return ""
        remaining = length - time
        return time_formatting(remaining // 1000)

    def get_position_percentage(self):
        return int(self.media.get_position() * 100)

    def reset(self):
        self.do_reset = False
        self.media.set_media(self.media.get_media())
        if config_get("repeatTracks") and not config_get("autonext"):
            self.media.play()
        elif config_get("autonext") and not config_get("repeatTracks"):
            if self.window:
                wx.CallAfter(self.window.next)

    def set_media(self, m, options=None):
        media = self.instance.media_new(m)
        if options:
            for opt in options:
                media.add_option(opt)
        self.media.set_media(media)
