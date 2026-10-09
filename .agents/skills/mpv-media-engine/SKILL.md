---
name: mpv-media-engine
description: >-
  Use when modifying or debugging media playback, libmpv-2.dll ctypes bindings,
  MPV event loop, audio output devices, equalizer filters, or playback timecodes and chapters.
---

# MPV Media Engine & Audio Processing

## Overview

HexPlayer relies on a low-level ctypes bridge to `libmpv-2.dll` (`src/media_player/mpv_backend.py`) for responsive, high-fidelity media playback. It manages asynchronous MPV event observation, WASAPI audio output routing, a 15-band audio equalizer, and chapter/timecode navigation without blocking the GUI.

## When to Use

- Interfacing with or modifying `libmpv-2.dll` via Python ctypes in `src/media_player/`.
- Diagnosing audio glitches, device switching failures (e.g. WASAPI Bluetooth/headphones), or volume/pitch drift.
- Configuring or debugging the 15-band graphic equalizer filter chain (FFmpeg `equalizer` peaking biquads plus `lowshelf`/`highshelf` end bands, driven through `lavfi`, with a `volume` preamp stage).
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

### 4. 15-Band Equalizer Filter String Formatting
The equalizer maps a preamp plus 15 per-band gains onto an FFmpeg audio-filter
chain built in `MpvMediaPlayer.apply_equalizer`. Bands sit on the standard
15-band ISO graphic-equalizer grid. The two extreme bands behave like a real
graphic EQ's end sliders: the lowest (25 Hz) is a **low-shelf** (`lowshelf`) and
the highest (16 kHz) is a **high-shelf** (`highshelf`), so they lift/cut
everything below/above the corner instead of only a narrow peak; the 13 bands in
between are peaking `equalizer` biquads. The preamp is a single leading `volume`
stage. Shelves use a Butterworth-ish `Q=0.7` (`_SHELF_Q`) for a smooth, ripple-
free transition; peaking bands keep `Q=2`. Gains are clamped to the `[-20, +20]`
dB range (`GAIN_MIN`/`GAIN_MAX` in `media_player/preset_library.py`); only bands
and a preamp that differ from 0 are emitted, and an empty chain clears the `af`
property. Presets inherit the shelves automatically — each preset's first/last
band gain now drives its low/high shelf, so no preset JSON change is required.

```python
# ISO centers (Hz): 25, 40, 63, 100, 160, 250, 400, 630, 1000,
#                   1600, 2500, 4000, 6300, 10000, 16000
filters = []
if abs(preamp) > 0.001:
    filters.append(f"volume={preamp:g}dB")
high_shelf_index = len(EQ_FREQUENCIES) - 1
for index, (frequency, gain) in enumerate(zip(EQ_FREQUENCIES, bands)):
    if abs(gain) <= 0.001:
        continue
    if index == 0:  # low shelf: lifts/cuts sub-bass below 25 Hz
        filters.append(f"lowshelf=f={frequency}:t=q:w=0.7:g={gain:g}")
    elif index == high_shelf_index:  # high shelf: all "air" above 16 kHz
        filters.append(f"highshelf=f={frequency}:t=q:w=0.7:g={gain:g}")
    else:
        # Q=2 (t=q:w=2) keeps the 2/3-octave bands from bleeding into each
        # other, so the chain tracks the per-band gains like a real graphic EQ.
        filters.append(f"equalizer=f={frequency}:t=q:w=2:g={gain:g}")

value = f"lavfi=[{','.join(filters)}]" if filters else ""
mpv.mpv_set_property_string(handle, b"af", value.encode("utf-8"))
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
| Hard-boosting many bands with no preamp cut | Summed band gains push the signal past 0 dBFS and clip | Keep gains within the ±20 dB clamp and lower the preamp (`volume=NdB`) on heavily boosted presets |
| Unhandled device disconnect | Playback silently terminates or crashes | Catch error and fallback to `"auto"` |

## Verification & Quality Gates

- **Unit/Mock Tests**: Run `uv run pytest tests/test_equalizer.py tests/test_preset_library.py tests/test_equalizer_dialog.py tests/test_media_gui_speed.py tests/test_timecodes.py tests/test_chapters.py`
- **Lint Check**: Run `uv run ruff check src/media_player/`
- **Manual Verification**:
  1. Play an audio/video stream.
  2. Test Play/Pause (Space), Seek (Left/Right Arrows), Volume (Up/Down Arrows).
  3. Change audio output device in Equalizer/Audio dialog and verify immediate switch.
