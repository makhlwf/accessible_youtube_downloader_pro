---
name: ytdlp-downloader-engine
description: >-
  Use when modifying or debugging media downloads, yt-dlp execution,
  format and quality selection, FFmpeg muxing, download progress events, or downloader self-healing updates.
---

# yt-dlp Downloader Engine & Self-Healing Pipeline

## Overview

HexPlayer's media download system (`src/download_handler/downloader.py`) coordinates multi-threaded downloads using `yt-dlp` and `ffmpeg.exe`. It features dynamic module loading (permitting in-app updates to `yt-dlp.zip` without rebuilding the desktop application), robust format selection, and throttled progress dispatches to ensure screen readers remain responsive throughout large downloads.

## When to Use

- Modifying or debugging download logic, video/audio formats, or download options in `src/download_handler/`.
- Resolving `yt-dlp` extraction failures, rate-limiting, or cipher issues.
- Handling download progress callbacks, speed calculations, or ETA formatting.
- Configuring FFmpeg remuxing, audio conversions (MP3, M4A, Opus), or thumbnail/metadata embedding.
- Managing the self-healing auto-updater for `yt-dlp.zip`.

**When NOT to use:**
- In-app media playback using MPV (use `mpv-media-engine`).
- Managing local favorites or history tables (use `sqlite-state-storage`).

## Core Patterns & Invariants

### 1. Dynamic `yt-dlp` Module Loading
`yt-dlp` is dynamically imported from `%APPDATA%\HexPlayer\yt_dlp.zip` or the application's root directory:

```python
# ✅ REQUIRED: Resolve yt-dlp dynamically via paths.py
import sys
from paths import get_ytdlp_zip_path

zip_path = get_ytdlp_zip_path()
if zip_path.exists() and str(zip_path) not in sys.path:
    sys.path.insert(0, str(zip_path))

import yt_dlp
```

### 2. Throttled Progress Hook Dispatches
yt-dlp invokes progress hooks frequently (multiple times per millisecond on fast networks). Never dispatch `wx.CallAfter` on every hook call:

```python
class DownloadProgressTracker:
    def __init__(self, callback):
        self.callback = callback
        self.last_dispatch_time = 0.0

    def hook(self, d):
        status = d.get("status")
        now = time.time()
        # Only dispatch to GUI every 200ms or on completion/error
        if status in ("finished", "error") or (now - self.last_dispatch_time > 0.2):
            self.last_dispatch_time = now
            wx.CallAfter(self.callback, d)
```

### 3. Graceful Thread Cancellation
Download worker threads must check a `threading.Event` cancellation token regularly. When canceled, clean up partial download files (`.part`):

```python
if cancel_event.is_set():
    raise DownloadCanceledException("User canceled download")
```

### 4. FFmpeg Location Discovery
Ensure `ffmpeg_location` in `ydl_opts` points to the application's bundled `ffmpeg.exe` and `ffprobe.exe` (`src/ffmpeg.exe`):

```python
ydl_opts["ffmpeg_location"] = str(paths.get_ffmpeg_path())
```

## Quick Reference

| Option Key | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `format` | `'bestvideo+bestaudio/best'` | Maximum video and audio quality |
| `outtmpl` | `'%(title)s.%(ext)s'` | Destination file naming convention |
| `noplaylist` | `True` / `False` | Single item vs entire playlist |
| `writethumbnail` | `True` | Embed thumbnail in output |
| `postprocessors` | `[{'key': 'FFmpegExtractAudio'}]` | Convert to MP3/M4A audio only |

## Implementation Procedures

### Step 1: Starting a Background Download
1. Collect target URL and format configuration from `DownloadDialog`.
2. Instantiate `DownloadThread(url, options, progress_callback, cancel_event)`.
3. Set daemon thread and start.
4. Announce start to screen reader:
   ```python
   speech_client.speak(_("Download started for {title}").format(title=title))
   ```

### Step 2: Handling Completion & Notification
1. In the progress hook, detect `status == 'finished'`.
2. Play accessible completion tone or announce:
   ```python
   speech_client.speak(_("Download completed: {title}").format(title=title))
   ```
3. Update `DownloadProgressDialog` or close progress window.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Flooding wx queue with progress events | Freezes GUI, locks screen reader speech | Throttle updates to ~5Hz (every 200ms) |
| Hardcoding `ffmpeg` in system PATH | Fails on user machines without FFmpeg installed | Point to bundled `src/ffmpeg.exe` |
| Blocking worker termination on cancel | Process leaves unclosed file handles | Catch cancel and call `os.remove` on `.part` |
| Assuming `yt_dlp` is in virtualenv | Breaks when running updated zip in AppData | Always load from dynamic path |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_downloader.py tests/test_download_dialog.py tests/test_download_menus.py`
- **Lint Check**: Run `uv run ruff check src/download_handler/`
- **Manual Verification**:
  1. Open a video in HexPlayer.
  2. Press `Ctrl+D` to open Download Dialog.
  3. Select audio (MP3 320kbps) and video (1080p MP4).
  4. Verify download progress updates, screen reader speech, and resulting file playability.
