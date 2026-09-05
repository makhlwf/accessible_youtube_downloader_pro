# Media Player Subsystem Rules (`src/media_player/`)

This directory contains the low-level media playback pipeline, ctypes bindings for `libmpv-2.dll`, equalizer filters, and chapter timecode utilities.

1. **Ctypes Memory Safety & Thread Boundaries**:
   - `libmpv-2.dll` functions interact across Python's GIL. Ensure all strings passed to `mpv_set_property_string` or `mpv_command` are properly encoded as UTF-8 bytes (`c_char_p(val.encode('utf-8'))`).
   - Any pointers returned by MPV that require deallocation must be freed using `mpv_free_node_contents` or appropriate MPV C APIs to prevent memory leaks.

2. **Event Dispatching via Custom Events**:
   - The MPV event observer loop runs in a dedicated background daemon thread (`mpv_event_loop`).
   - It must never invoke wx methods directly. It must post custom wx events (`EVT_MPV_EVENT`) or use `wx.CallAfter` to notify the player GUI.

3. **Audio Output & WASAPI Devices**:
   - Device switching must handle disconnected Bluetooth/WASAPI endpoints gracefully, falling back to `auto` without crashing playback.

4. **Equalizer Filter Formats**:
   - 10-band equalizer settings are mapped to ffmpeg filter syntax (`firequalizer` or `equalizer`).
   - Validate numerical gain boundaries (-12dB to +12dB) before sending filter strings to MPV.

5. **Chapter & Timecode Navigation**:
   - Announce chapter name and timestamp via `speech_client.speak` when seeking between chapters.
