---
name: mpv-media-engine
description: >-
  Use when modifying or debugging media playback, libmpv-2.dll ctypes bindings,
  MPV event loop, audio output devices, equalizer filters, or playback timecodes and chapters.
---

# MPV Media Engine & Audio Processing

## Overview

HexPlayer relies on a low-level ctypes bridge to `libmpv-2.dll` (`src/media_player/mpv_backend.py`) for responsive, high-fidelity media playback. It manages asynchronous MPV event observation, WASAPI audio output routing, a 10-band audio equalizer, and chapter/timecode navigation without blocking the GUI.

## When to Use

- Interfacing with or modifying `libmpv-2.dll` via Python ctypes in `src/media_player/`.
- Diagnosing audio glitches, device switching failures (e.g. WASAPI Bluetooth/headphones), or volume/pitch drift.
- Configuring or debugging the 10-band graphic equalizer filter chains (`firequalizer` / `equalizer`).
- Handling chapter markers, timecodes, subtitle tracks, or playback speed adjustments.
- Investigating MPV event loop crashes or memory leaks during seek/pause/stop operations.

**When NOT to use:**
- Handling YouTube video search or downloading (use `ytdlp-downloader-engine` or `innertube-rpc-bridge`).

## Core Patterns & Invariants

### 1. Ctypes Memory & String Safety
All strings passed to MPV C functions must be UTF-8 encoded byte strings. Never pass raw Python `str` objects to ctypes C-pointers:

```python
# ❌ INCORRECT: Passing str directly to ctypes
mpv.mpv_set_property_string(handle, "pause", "yes")  # TypeError or memory corruption


# ✅ CORRECT: Encoded as UTF-8 bytes
def set_mpv_property(handle, name: str, value: str):
    b_name = name.encode("utf-8")
    b_value = value.encode("utf-8")
    return mpv.mpv_set_property_string(handle, b_name, b_value)
```

### 2. Dedicated Event Loop Thread
The MPV event loop (`mpv_wait_event`) must run continuously in a background daemon thread. It translates MPV C events (`MPV_EVENT_PROPERTY_CHANGE`, `MPV_EVENT_END_FILE`) into wxPython events:

```python
# ✅ REQUIRED: Thread loop polling mpv_wait_event
def _mpv_event_loop(self):
    while self._running:
        event = mpv.mpv_wait_event(self.handle, 0.1)
        if event.contents.event_id == MPV_EVENT_NONE:
            continue
        if event.contents.event_id == MPV_EVENT_PROPERTY_CHANGE:
            wx.CallAfter(self._on_property_changed, event)
```

### 3. WASAPI Audio Endpoint Switching
When the user changes audio devices, resolve the WASAPI device GUID or ID:

```python
# Query devices:
devices = mpv_backend.get_available_audio_output_devices()
# Switch device safely:
mpv.mpv_set_property_string(handle, b"audio-device", selected_device_id.encode("utf-8"))
```

### 4. 10-Band Equalizer Filter String Formatting
Equalizer settings map to FFmpeg audio filter syntax. Gains must remain clamped between -12dB and +12dB to prevent clipping distortion:

```python
# Frequencies: 31Hz, 62Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz
filter_str = f"firequalizer=gain_entry='entry(31,{g0});entry(62,{g1});entry(125,{g2});entry(250,{g3});entry(500,{g4});entry(1000,{g5});entry(2000,{g6});entry(4000,{g7});entry(8000,{g8});entry(16000,{g9})'"
mpv.mpv_set_property_string(handle, b"af", filter_str.encode("utf-8"))
```

## Quick Reference

| Action | Function / Method |
| :--- | :--- |
| **Load File / URL** | `mpv_command_string(handle, f"loadfile \"{url}\"")` |
| **Seek Position** | `mpv_command_string(handle, f"seek {seconds} absolute")` |
| **Pause / Resume** | `mpv_set_property_string(handle, b"pause", b"yes"/"no")` |
| **Set Playback Speed** | `mpv_set_property_string(handle, b"speed", str(rate).encode())` |
| **Observe Property** | `mpv_observe_property(handle, reply_id, b"time-pos", MPV_FORMAT_DOUBLE)` |
| **Enumerate Audio Devices** | `mpv_backend.get_available_audio_output_devices(force_refresh=True)` |

## Implementation Procedures

### Step 1: Handling Audio Output Switching Gracefully
1. Call `get_available_audio_output_devices()`.
2. Find the device matching the stored setting in `%APPDATA%\HexPlayer\settings.ini`.
3. If the device is disconnected, fallback to `"auto"`.
4. Apply using `set_property("audio-device", dev_id)`.
5. Announce device change to the user:
   ```python
   speech_client.speak(_("Audio device set to {name}").format(name=device_name))
   ```

### Step 2: Adding Chapter & Timecode Jumping
1. Extract video chapters via MPV property `chapter-list`.
2. When the user presses `[` or `]`, seek to previous/next chapter boundary.
3. Fetch the new chapter title:
   ```python
   chapter_title = player.get_current_chapter_title()
   speech_client.speak(chapter_title)
   ```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Blocking the UI thread with `mpv_wait_event` | Freezes the GUI completely | Run `mpv_wait_event` in daemon thread |
| Passing unencoded strings | Python ctypes crashes on 64-bit Windows | Always `.encode('utf-8')` strings |
| Equalizer gain > 12dB | Severe digital clipping and distortion | Clamp sliders to [-12, +12] |
| Unhandled device disconnect | Playback silently terminates or crashes | Catch error and fallback to `"auto"` |

## Verification & Quality Gates

- **Unit/Mock Tests**: Run `uv run pytest tests/test_equalizer.py tests/test_media_gui_speed.py tests/test_timecodes.py tests/test_chapters.py`
- **Lint Check**: Run `uv run ruff check src/media_player/`
- **Manual Verification**:
  1. Play an audio/video stream.
  2. Test Play/Pause (Space), Seek (Left/Right Arrows), Volume (Up/Down Arrows).
  3. Change audio output device in Equalizer/Audio dialog and verify immediate switch.
