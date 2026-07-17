import wx
from threading import Thread

from media_player.equalizer import EqualizerService
from media_player.mpv_backend import MpvMedia, MpvMediaPlayer, State
from settings_handler import config_get
from utils import time_formatting


class Player:
    def __init__(self, filename, hwnd, window=None, options=None):
        self.eq = None
        self.do_reset = False
        self.window = window
        self.filename = filename
        self.hwnd = hwnd
        self.media = MpvMediaPlayer(hwnd=self.hwnd or None, end_callback=self.onEnd)
        if config_get("eq_enabled"):
            self.eq = EqualizerService()
            self.eq.load_settings()
            self.eq.apply_to_player(self.media)
        self.set_media(self.filename, options)
        self.media.play()
        self.volume = int(config_get("volume"))
        self.media.audio_set_volume(self.volume)
        self._cached_length = -1

    def onEnd(self, event=None):
        self.do_reset = True
        Thread(target=self.reset).start()

    def get_length(self):
        if self._cached_length == -1:
            self._cached_length = self.media.get_length()
        return self._cached_length

    def seek(self, seconds):
        length = self.get_length()
        if length == -1:
            return 0.03
        try:
            return seconds / (length / 1000)
        except ZeroDivisionError:
            return 0.03

    def get_duration(self):
        duration = self.get_length()
        if duration == -1 or not isinstance(duration, int):
            return ""
        return time_formatting(duration // 1000)

    def get_elapsed(self):
        elapsed = self.media.get_time()
        if elapsed == -1 or not isinstance(elapsed, int):
            return ""
        return time_formatting(elapsed // 1000)

    def get_remaining(self):
        length = self.get_length()
        time = self.media.get_time()
        if length == -1 or time == -1:
            return ""
        remaining = length - time
        return time_formatting(remaining // 1000)

    def get_position_percentage(self):
        position = self.media.get_position()
        if position < 0:
            return -1
        return int(position * 100)

    def reset(self):
        self.do_reset = False
        current_media = self.media.get_media()
        if current_media is not None:
            self.media.set_media(current_media)
        if config_get("repeatTracks") and not config_get("autonext"):
            self.media.play()
        elif config_get("autonext") and not config_get("repeatTracks"):
            if self.window:
                wx.CallAfter(self.window.next)

    def set_media(self, m, options=None):
        media = MpvMedia(m, options)
        self.media.set_media(media)
        self._cached_length = -1


__all__ = ["Player", "State"]
