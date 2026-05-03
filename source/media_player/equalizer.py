import vlc
from typing import Any


class EqualizerService:
    """Service to manage VLC audio equalizer settings."""

    def __init__(self) -> None:
        """Initialize the equalizer service."""
        self.equalizer = vlc.AudioEqualizer()
        self.preamp: float = 0.0

    def set_preamp(self, value: float) -> None:
        """Set the preamp level.

        Args:
            value: Preamp value (typically -20.0 to 20.0).
        """
        if not -20.0 <= value <= 20.0:
            raise ValueError("Preamp value out of range (-20.0 to 20.0).")
        self.preamp = value
        self.equalizer.set_preamp(value)

    def set_band(self, index: int, value: float) -> None:
        """Set the gain for a specific equalizer band.

        Args:
            index: Band index (0 to 19).
            value: Gain value (typically -20.0 to 20.0).
        """
        if not 0 <= index <= 19:
            raise ValueError("Index out of range (0 to 19).")
        if not -20.0 <= value <= 20.0:
            raise ValueError("Gain value out of range (-20.0 to 20.0).")
        self.equalizer.set_amp_at_index(value, index)

    def apply_to_player(self, player: Any) -> None:
        """Apply the current equalizer settings to a VLC player.

        Args:
            player: The VLC player instance.
        """
        player.set_equalizer(self.equalizer)
