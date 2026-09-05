# Downloader Subsystem Rules (`src/download_handler/`)

This directory contains the media download engine, `yt-dlp` integration, progress tracking, and format selection.

1. **Dynamic yt-dlp Loading**:
   - `yt-dlp` is loaded dynamically from `%APPDATA%\HexPlayer\yt_dlp.zip` or the application root bundle.
   - Do not assume a static pre-installed `yt_dlp` pip package is present.

2. **Thread Safety & Cancellation**:
   - Downloads run in background worker threads.
   - Support graceful cancellation via thread-safe `threading.Event` cancellation tokens.
   - Close temporary file handles cleanly if a download is canceled or encounters an error.

3. **Progress Hook Rate-Limiting**:
   - yt-dlp progress hooks can fire dozens of times per second.
   - Throttle GUI dispatches using time stamps (e.g., dispatch at most every 100-250ms) to avoid saturating the wxPython event queue with `wx.CallAfter` calls.

4. **FFmpeg Post-Processing**:
   - Verify `ffmpeg.exe` and `ffprobe.exe` existence before executing post-processors (audio extraction, video remuxing, thumbnail embedding).
