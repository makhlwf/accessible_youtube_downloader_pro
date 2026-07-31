from typing import Any, ClassVar


class EqualizerService:
    """Service to manage MPV audio equalizer settings."""

    PRESETS: ClassVar[dict[str, dict[str, Any]]] = {
        "Flat": {"preamp": 0.0, "bands": [0.0] * 10},
        "Rock": {
            "preamp": 5.0,
            "bands": [8.0, 5.0, -5.0, -8.0, -3.0, 3.0, 8.0, 11.0, 11.0, 11.0],
        },
        "Pop": {
            "preamp": -2.0,
            "bands": [-2.0, -1.0, 3.0, 7.0, 7.0, 5.0, 0.0, -2.0, -2.0, -2.0],
        },
        "Jazz": {
            "preamp": 2.0,
            "bands": [0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 0.0, 3.0, 5.0, 5.0],
        },
        "Classical": {
            "preamp": 0.0,
            "bands": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -5.0, -5.0, -5.0, -8.0],
        },
    }

    def __init__(self) -> None:
        """Initialize the equalizer service."""
        self.equalizer = self
        self.preamp: float = 0.0
        self.bands: list[float] = [0.0] * 10

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
            index: Band index (0 to 9).
            value: Gain value (typically -20.0 to 20.0).
        """
        if not 0 <= index <= 9:
            raise ValueError("Index out of range (0 to 9).")
        if not -20.0 <= value <= 20.0:
            raise ValueError("Gain value out of range (-20.0 to 20.0).")
        self.bands[index] = value

    def get_band(self, index: int) -> float:
        """Get the gain for a specific equalizer band.

        Args:
            index: Band index (0 to 9).

        Returns:
            Gain value.
        """
        if not 0 <= index <= 9:
            raise ValueError("Index out of range (0 to 9).")
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
        """Load equalizer settings from configuration."""
        import settings_handler

        preamp = settings_handler.config_get("eq_preamp")
        if preamp is not None:
            try:
                self.set_preamp(float(preamp))
            except ValueError, TypeError:
                pass

        bands_str = settings_handler.config_get("eq_bands")
        if bands_str:
            try:
                band_values = [float(v) for v in bands_str.split(",")]
                for i, value in enumerate(band_values):
                    if i < 10:
                        self.set_band(i, value)
            except ValueError, TypeError:
                pass

    def save_settings(self) -> None:
        """Save current equalizer settings to configuration."""
        import settings_handler

        settings_handler.config_set("eq_preamp", self.preamp)
        bands_str = ",".join(str(v) for v in self.bands)
        settings_handler.config_set("eq_bands", bands_str)

    def reset(self) -> None:
        """Reset equalizer to flat settings (0 gain on all bands and preamp)."""
        self.set_preamp(0.0)
        for i in range(10):
            self.set_band(i, 0.0)

    def apply_to_player(self, player: Any) -> None:
        """Apply the current equalizer settings to an MPV player."""
        if hasattr(player, "set_equalizer"):
            player.set_equalizer(self)

    def apply_to_mpv(self, player: Any) -> None:
        """Apply the current equalizer settings to the MPV backend."""
        player.apply_equalizer(self.preamp, self.bands)
