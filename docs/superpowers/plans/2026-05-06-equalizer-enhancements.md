# Equalizer Service Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `EqualizerService` with presets support, settings storage (load/save), and reset functionality.

**Architecture:** Update `EqualizerService` to use `settings_handler` for persistence. Add a static `PRESETS` dictionary for standard VLC profiles.

**Tech Stack:** Python, VLC (python-vlc), pytest.

---

### Task 1: Write failing tests for presets and storage

**Files:**
- Modify: `tests/test_equalizer.py`

- [ ] **Step 1: Add tests for presets and storage**

```python
import pytest
from unittest.mock import MagicMock, patch
from media_player.equalizer import EqualizerService
import settings_handler

def test_get_band():
    eq = EqualizerService()
    eq.set_band(0, 5.0)
    assert eq.get_band(0) == 5.0

def test_presets():
    eq = EqualizerService()
    eq.apply_preset("Rock")
    # Verify some band values for Rock (index 0 is 8.0)
    assert eq.get_band(0) == 8.0

def test_load_settings():
    with patch("settings_handler.config_get") as mock_get:
        def side_effect(key):
            if key == "eq_bands":
                return "1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0"
            if key == "eq_preamp":
                return 5.0
            return None
        mock_get.side_effect = side_effect
        
        eq = EqualizerService()
        eq.load_settings()
        assert eq.preamp == 5.0
        assert eq.get_band(0) == 1.0
        assert eq.get_band(9) == 10.0

def test_save_settings():
    with patch("settings_handler.config_set") as mock_set:
        eq = EqualizerService()
        eq.set_preamp(3.0)
        eq.set_band(0, 1.0)
        eq.set_band(1, 2.0)
        # ... other bands 0.0
        eq.save_settings()
        
        mock_set.assert_any_call("eq_preamp", 3.0)
        # The expected bands string for 1.0, 2.0, then 8 zeros
        expected_bands = "1.0,2.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0"
        mock_set.assert_any_call("eq_bands", expected_bands)

def test_reset():
    eq = EqualizerService()
    eq.set_preamp(5.0)
    eq.set_band(0, 5.0)
    eq.reset()
    assert eq.preamp == 0.0
    assert eq.get_band(0) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_equalizer.py -v`
Expected: FAIL (AttributeError: 'EqualizerService' object has no attribute 'get_band', etc.)

### Task 2: Implement missing methods and PRESETS in EqualizerService

**Files:**
- Modify: `source/media_player/equalizer.py`

- [ ] **Step 1: Implement PRESETS and methods**

```python
import vlc
from typing import Any, Dict, List
import settings_handler

class EqualizerService:
    """Service to manage VLC audio equalizer settings."""

    PRESETS: Dict[str, List[float]] = {
        "Flat": [0.0] * 10,
        "Rock": [8.0, 5.0, -5.0, -8.0, -3.0, 3.0, 8.0, 11.0, 11.0, 11.0],
        "Pop": [-2.0, -1.0, 3.0, 7.0, 7.0, 5.0, 0.0, -2.0, -2.0, -2.0],
        "Jazz": [0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 0.0, 3.0, 5.0, 5.0],
        "Classical": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -5.0, -5.0, -5.0, -8.0],
    }

    def __init__(self) -> None:
        """Initialize the equalizer service."""
        self.equalizer = vlc.AudioEqualizer()
        self.preamp: float = 0.0
        self.bands: List[float] = [0.0] * 10

    def set_preamp(self, value: float) -> None:
        """Set the preamp level."""
        if not -20.0 <= value <= 20.0:
            raise ValueError("Preamp value out of range (-20.0 to 20.0).")
        self.preamp = value
        self.equalizer.set_preamp(value)

    def set_band(self, index: int, value: float) -> None:
        """Set the gain for a specific equalizer band."""
        if not 0 <= index <= 9: # Corrected to 10 bands
            raise ValueError("Index out of range (0 to 9).")
        if not -20.0 <= value <= 20.0:
            raise ValueError("Gain value out of range (-20.0 to 20.0).")
        self.bands[index] = value
        self.equalizer.set_amp_at_index(value, index)

    def get_band(self, index: int) -> float:
        """Get the gain for a specific equalizer band."""
        if not 0 <= index <= 9:
            raise ValueError("Index out of range (0 to 9).")
        return self.bands[index]

    def apply_preset(self, name: str) -> None:
        """Apply a named preset."""
        if name not in self.PRESETS:
            raise ValueError(f"Unknown preset: {name}")
        preset_values = self.PRESETS[name]
        for i, value in enumerate(preset_values):
            self.set_band(i, value)

    def load_settings(self) -> None:
        """Load settings from the configuration."""
        self.set_preamp(settings_handler.config_get("eq_preamp"))
        bands_str = settings_handler.config_get("eq_bands")
        if bands_str:
            try:
                bands = [float(b) for b in bands_str.split(",")]
                for i, value in enumerate(bands):
                    if i < 10:
                        self.set_band(i, value)
            except (ValueError, TypeError):
                pass

    def save_settings(self) -> None:
        """Save current settings to the configuration."""
        settings_handler.config_set("eq_preamp", self.preamp)
        bands_str = ",".join(str(b) for b in self.bands)
        settings_handler.config_set("eq_bands", bands_str)

    def reset(self) -> None:
        """Reset equalizer to flat settings."""
        self.set_preamp(0.0)
        for i in range(10):
            self.set_band(i, 0.0)

    def apply_to_player(self, player: Any) -> None:
        """Apply the current equalizer settings to a VLC player."""
        player.set_equalizer(self.equalizer)
```

- [ ] **Step 2: Update validation in tests**

Since I'm changing 20 bands to 10 bands, I need to update the existing tests in `tests/test_equalizer.py`.

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_equalizer.py -v`
Expected: PASS

- [ ] **Step 4: Commit changes**
