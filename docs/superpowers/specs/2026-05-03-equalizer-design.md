# Equalizer Feature Design Document

## Overview
Implement a fully accessible, persistent 10-band equalizer for the media player with live update capability.

## Data Persistence & Settings
- Storage via `settings_handler.py`.
- New keys in `settings.ini`:
    - `eq_enabled` (bool)
    - `eq_preamp` (float)
    - `eq_bands` (string: comma-separated floats)
    - `eq_preset` (string/int)
- Settings loaded on player initialization.

## Backend (Equalizer Service)
- New file: `source/media_player/equalizer.py`.
- Wraps `vlc.AudioEqualizer`.
- Methods: `set_band(index, value)`, `set_preamp(value)`, `apply_to_player(player)`.

## Frontend (GUI)
- New file: `source/gui/equalizer_dialog.py`.
- `wx.Dialog` containing:
    - 10 sliders for frequency bands (accessible via screen readers).
    - 1 slider for pre-amp gain.
    - Preset selection dropdown.
- Live updates to the active `vlc` instance.

## Testing
- New file: `tests/test_equalizer.py`.
- Tests: settings persistence, API communication, preset application.
