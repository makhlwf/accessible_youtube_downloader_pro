---
name: clipboard-url-monitor
description: >-
  Use when modifying or debugging clipboard YouTube URL detection,
  background clipboard polling threads, or auto-detect player dialogs.
---

# Clipboard YouTube URL Monitoring & Auto-Detection

## Overview

HexPlayer includes a background clipboard monitoring subsystem (`src/gui/auto_detect_dialog.py` and `src/utils.py`) that observes the Windows system clipboard. When a blind user copies a YouTube link in their browser, Discord, or an email, HexPlayer automatically intercepts the URL, presents an accessible `AutoDetectDialog`, and prompts them to Play or Download the content with a single keystroke.

## When to Use

- Modifying the clipboard watcher daemon thread or polling interval in `src/accessible_youtube_downloader_pro.py`.
- Handling Windows clipboard API locks (`pyperclip.PyperclipWindowsException` / `OpenClipboard failed`).
- Updating YouTube URL regex matchers for new URL patterns (`youtu.be`, `youtube.com/shorts/`, `music.youtube.com`).
- Adjusting focus behavior, screen reader announcements, or options in `AutoDetectDialog`.
- Preventing duplicate prompts for the same copied URL.

**When NOT to use:**
- Handling browser extension native messaging (use `chrome-native-messaging`).

## Core Patterns & Invariants

### 1. Robust Clipboard Polling with Lock Resilience
Other Windows applications frequently hold transient clipboard locks. The watcher thread must retry gracefully without crashing or logging repetitive errors:

```python
# ✅ REQUIRED: Catch clipboard lock exceptions gracefully
import time
import pyperclip


def get_clipboard_text_safe() -> str | None:
    for attempt in range(3):
        try:
            return pyperclip.paste()
        except Exception:
            time.sleep(0.05)
    return None
```

### 2. URL Deduplication & Pattern Matching
Do not prompt the user for the same URL twice in a row, and ignore non-YouTube clipboard contents:

```python
from youtube_url_utils import is_valid_youtube_url, extract_video_id

current_text = get_clipboard_text_safe()
if current_text and current_text != self.last_handled_clipboard:
    self.last_handled_clipboard = current_text
    if is_valid_youtube_url(current_text):
        wx.CallAfter(self._show_auto_detect_dialog, current_text)
```

### 3. Accessible AutoDetectDialog Focus Protocol
When `AutoDetectDialog` opens:
1. Speak prompt immediately:
   ```python
   speech_client.speak(
       _("YouTube link detected. Press Enter to play or Tab for options."), interrupt=True
   )
   ```
2. Set default button to "Play" (`wx.ID_OK`).
3. If dismissed with Escape (`wx.ID_CANCEL`), close cleanly and restore focus to the active window.

## Quick Reference

| Feature | Location / Setting |
| :--- | :--- |
| **Watcher Thread** | Background daemon thread in `accessible_youtube_downloader_pro.py` |
| **Dialog Implementation** | `src/gui/auto_detect_dialog.py` |
| **Setting Key** | `config_get("auto_detect_clipboard")` (`True` / `False`) |
| **URL Validation** | `src/youtube_url_utils.py` |

## Implementation Procedures

### Step 1: Handling Detected Clipboard Link
1. In watcher loop, if new YouTube URL is found:
2. Dispatch to UI thread: `wx.CallAfter(self._on_clipboard_link_detected, url)`.
3. In `_on_clipboard_link_detected`:
   - If app is currently busy or a modal dialog is open, queue or display non-intrusive prompt.
   - Otherwise, instantiate `AutoDetectDialog(self, url)` and call `dlg.Show()`.

### Step 2: Testing Clipboard Monitoring
Run automated clipboard monitoring tests:
```powershell
uv run pytest tests/test_clipboard_monitoring.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Polling clipboard too frequently (e.g. 10ms) | High CPU usage, clipboard lock contention | Poll every 500ms to 1000ms |
| Unhandled `pyperclip` Windows error | Watcher thread terminates silently | Catch exceptions in retry loop |
| Re-prompting for the same URL | Irritates user when switching between apps | Cache `last_handled_clipboard` |
| Stealing focus aggressively | Interrupts user typing in other applications | Test window active state before popup |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_clipboard_monitoring.py`
- **Lint Check**: Run `uv run ruff check src/gui/auto_detect_dialog.py`
- **Manual Verification**:
  1. Launch HexPlayer with clipboard auto-detect enabled.
  2. Copy a YouTube URL in Notepad or browser (`Ctrl+C`).
  3. Verify `AutoDetectDialog` appears within 1 second and announces link to NVDA/JAWS.
