import logging
from threading import Thread

import wx

from media_player.equalizer import EqualizerService
from media_player.mpv_backend import MpvMedia, MpvMediaPlayer, State
from settings_handler import config_get, config_set
from utils import time_formatting

logger = logging.getLogger(__name__)
DEFAULT_AUDIO_OUTPUT_DEVICE = ""


class Player:
    def __init__(self, filename, hwnd, window=None, options=None):
        self.eq = None
        self.do_reset = False
        self._closing = False
        self.window = window
        self.filename = filename
        self.hwnd = hwnd
        self.media = MpvMediaPlayer(hwnd=self.hwnd or None, end_callback=self.onEnd)
        if config_get("eq_enabled"):
            self.eq = EqualizerService()
            self.eq.load_settings()
            self.eq.apply_to_player(self.media)
        self.apply_saved_audio_output_device()
        self.set_media(self.filename, options)
        self.media.play()
        self.volume = int(config_get("volume"))
        self.media.audio_set_volume(self.volume)
        self._cached_length = -1

    def onEnd(self, event=None):
        if self._closing:
            return
        self.do_reset = True
        Thread(target=self.reset, daemon=True).start()

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
        if self._closing:
            return
        self.do_reset = False
        current_media = self.media.get_media()
        if current_media is not None:
            self.media.set_media(current_media)
            self.apply_saved_audio_output_device()
        if getattr(self.window, "shorts_mode", False) or (
            config_get("repeatTracks") and not config_get("autonext")
        ):
            self.media.play()
        elif config_get("autonext") and not config_get("repeatTracks") and self.window:
            wx.CallAfter(self.window.next)

    def set_media(self, m, options=None):
        media = MpvMedia(m, options)
        self.media.set_media(media)
        self._cached_length = -1

    def get_audio_output_devices(self):
        try:
            return self.media.get_audio_output_devices()
        except Exception:
            logger.exception("Could not enumerate MPV audio output devices")
            return []

    def get_selected_audio_output_device(self):
        device_id = config_get("audiooutputdevice")
        if device_id is None or device_id == "None":
            return DEFAULT_AUDIO_OUTPUT_DEVICE
        return str(device_id)

    def get_current_audio_output_device(self):
        try:
            return self.media.get_audio_output_device()
        except Exception:
            logger.exception("Could not get current MPV audio output device")
            return DEFAULT_AUDIO_OUTPUT_DEVICE

    def _get_audio_output_device_connection_status(self, device_id):
        devices = self.get_audio_output_devices()
        if not devices:
            logger.info(
                "MPV did not return audio output devices; keeping configured device. device_id=%s",
                device_id,
            )
            return None
        return any(device["id"] == device_id for device in devices)

    def apply_saved_audio_output_device(self):
        device_id = self.get_selected_audio_output_device()
        if not device_id:
            logger.info(
                "No custom audio output device configured; using system default"
            )
            return True
        return self.select_audio_output_device(
            device_id,
            notify_on_fallback=True,
            reset_on_failure=True,
        )

    def select_audio_output_device(
        self, device_id, notify_on_fallback=False, reset_on_failure=True
    ):
        device_id = device_id or DEFAULT_AUDIO_OUTPUT_DEVICE
        if device_id == DEFAULT_AUDIO_OUTPUT_DEVICE:
            return self.reset_audio_output_device_to_default()

        connection_status = self._get_audio_output_device_connection_status(device_id)
        if connection_status is False:
            logger.warning(
                "Selected audio output device is not connected. device_id=%s",
                device_id,
            )
            if reset_on_failure:
                self.reset_audio_output_device_to_default(notify=notify_on_fallback)
            return False

        try:
            selected = self.media.set_audio_output_device(device_id)
        except Exception:
            logger.exception(
                "Could not select MPV audio output device. device_id=%s", device_id
            )
            selected = False

        if not selected:
            if reset_on_failure:
                self.reset_audio_output_device_to_default(notify=notify_on_fallback)
            return False

        logger.info("Selected audio output device. device_id=%s", device_id)
        config_set("audiooutputdevice", device_id)
        return True

    def reset_audio_output_device_to_default(self, notify=False):
        try:
            self.media.set_audio_output_device(DEFAULT_AUDIO_OUTPUT_DEVICE)
        except Exception:
            logger.exception("Could not reset MPV audio output device to default")
        logger.info("Using default audio output device")
        config_set("audiooutputdevice", DEFAULT_AUDIO_OUTPUT_DEVICE)
        if notify:
            self._notify_audio_output_fallback()
        return True

    def _notify_audio_output_fallback(self):
        if self.window is not None and hasattr(self.window, "on_audio_output_fallback"):
            self.window.on_audio_output_fallback()

    def close(self):
        self._closing = True
        self.window = None
        if self.media is None:
            return
        try:
            self.media.stop()
        except Exception:
            logger.exception("Could not stop MPV during player close")
        try:
            self.media.close()
        except Exception:
            logger.exception("Could not close MPV during player close")


__all__ = ["Player", "State"]
