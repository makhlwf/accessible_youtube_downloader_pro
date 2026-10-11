from typing import Any, ClassVar

from media_player.preset_library import (
    BAND_COUNT,
    GAIN_MAX,
    GAIN_MIN,
    load_presets,
)


class EqualizerService:
    """Service to manage MPV audio equalizer settings.

    Each preset holds a preamp level in dB plus one gain (dB) per band, ordered
    from the lowest frequency to the highest across the standard 15-band ISO
    graphic-equalizer grid:
    25, 40, 63, 100, 160, 250, 400, 630, 1k, 1.6k, 2.5k, 4k, 6.3k, 10k, 16k Hz.
    The preamp compensates the overall level so heavily boosted presets do not
    clip. Preset keys are stored in the settings file, so they must stay stable;
    only their translated labels change (see gui/equalizer_dialog.py).

    Presets are defined in the ``eq_presets`` data directory, one JSON file per
    preset, and loaded once here (see media_player/preset_library.py).
    """

    PRESETS: ClassVar[dict[str, dict[str, Any]]] = load_presets()

    def __init__(self) -> None:
        """Initialize the equalizer service."""
        self.equalizer = self
        self.preamp: float = 0.0
        self.bands: list[float] = [0.0] * BAND_COUNT

    def set_preamp(self, value: float) -> None:
        """Set the preamp level.

        Args:
            value: Preamp value (typically -20.0 to 20.0).
        """
        if not -20.0 <= value <= 20.0:
            raise ValueError("Preamp value out of range (-20.0 to 20.0).")
        self.preamp = value

    def get_preamp(self) -> float:
        """Get the current preamp level.

        Returns:
            Preamp value.
        """
        return self.preamp

    def set_band(self, index: int, value: float) -> None:
        """Set the gain for a specific equalizer band.

        Args:
            index: Band index (0 to 14).
            value: Gain value (typically -20.0 to 20.0).
        """
        if not 0 <= index < BAND_COUNT:
            raise ValueError(f"Index out of range (0 to {BAND_COUNT - 1}).")
        if not -20.0 <= value <= 20.0:
            raise ValueError("Gain value out of range (-20.0 to 20.0).")
        self.bands[index] = value

    def get_band(self, index: int) -> float:
        """Get the gain for a specific equalizer band.

        Args:
            index: Band index (0 to 14).

        Returns:
            Gain value.
        """
        if not 0 <= index < BAND_COUNT:
            raise ValueError(f"Index out of range (0 to {BAND_COUNT - 1}).")
        return self.bands[index]

    def apply_preset(self, name: str) -> None:
        """Apply a named equalizer preset.

        Args:
            name: Preset name (e.g., "Rock", "Pop").
        """
        if name not in self.PRESETS:
            raise ValueError(f"Unknown preset: {name}")
        preset_data = self.PRESETS[name]
        self.set_preamp(preset_data["preamp"])
        for i, value in enumerate(preset_data["bands"]):
            self.set_band(i, value)

    def load_settings(self) -> None:
        """Load equalizer settings from configuration, tolerating bad data.

        Corrupt or hand-edited settings must never crash startup, so each value
        is parsed independently: an unreadable preamp is ignored (the current
        value is kept), while individual band gains are clamped into range and
        malformed band entries are skipped.

        Band counts have changed across versions (10 -> 15). A stored ``eq_bands``
        string whose length no longer matches ``BAND_COUNT`` cannot be mapped
        onto the current frequency grid, so instead of applying a wrong-frequency
        curve we fall back to the saved preset's bands when it names a known one,
        and otherwise leave the bands flat.
        """
        import settings_handler

        preamp = settings_handler.config_get("eq_preamp")
        if preamp is not None:
            try:
                value = float(preamp)
            except TypeError, ValueError:
                value = None
            if value is not None and GAIN_MIN <= value <= GAIN_MAX:
                self.preamp = value

        bands_str = settings_handler.config_get("eq_bands")
        tokens = [t.strip() for t in str(bands_str).split(",")] if bands_str else []

        if len(tokens) == BAND_COUNT:
            for index, token in enumerate(tokens):
                if not token:
                    continue
                try:
                    gain = float(token)
                except TypeError, ValueError:
                    continue
                self.bands[index] = max(GAIN_MIN, min(GAIN_MAX, gain))
            return

        # Legacy or malformed band string: migrate from the saved preset if we
        # can, otherwise keep the flat defaults.
        preset = settings_handler.config_get("eq_preset")
        if preset in self.PRESETS:
            for index, gain in enumerate(self.PRESETS[preset]["bands"]):
                self.bands[index] = gain

    def save_settings(self) -> None:
        """Save current equalizer settings to configuration."""
        import settings_handler

        settings_handler.config_set("eq_preamp", self.preamp)
        bands_str = ",".join(str(v) for v in self.bands)
        settings_handler.config_set("eq_bands", bands_str)

    def reset(self) -> None:
        """Reset equalizer to flat settings (0 gain on all bands and preamp)."""
        self.set_preamp(0.0)
        for i in range(BAND_COUNT):
            self.set_band(i, 0.0)

    def apply_to_player(self, player: Any) -> None:
        """Apply the current equalizer settings to an MPV player."""
        if hasattr(player, "set_equalizer"):
            player.set_equalizer(self)

    def apply_to_mpv(self, player: Any) -> None:
        """Apply the current equalizer settings to the MPV backend."""
        player.apply_equalizer(self.preamp, self.bands)
