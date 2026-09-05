---
name: sponsorblock-engine
description: >-
  Use when configuring or debugging SponsorBlock segment skipping,
  category filters, API timeouts, or MPV chapter segment boundaries.
---

# SponsorBlock Engine & Segment Skipping Subsystem

## Overview

HexPlayer integrates **SponsorBlock** (`src/sponsorblock_handler.py`) via `sponsorblock-py` to automatically detect and skip sponsor segments, intro animations, outro cards, and self-promotional content during media playback. When MPV's playback cursor crosses into an active sponsor segment, HexPlayer executes an instant seek jump to the segment boundary and announces the skip to the screen reader.

## When to Use

- Modifying or debugging SponsorBlock segment fetching in `src/sponsorblock_handler.py`.
- Handling SponsorBlock API network timeouts, caching, or rate limits.
- Configuring enabled skip categories (sponsor, intro, outro, selfpromo, interaction, music_offtopic).
- Integrating segment boundaries with MPV playback cursor observation (`time-pos`).
- Adjusting screen reader auditory skip notifications via `speech_client`.

**When NOT to use:**
- In-app media download postprocessing (use `ytdlp-downloader-engine`).

## Core Patterns & Invariants

### 1. Asynchronous Segment Retrieval
SponsorBlock API queries must occur asynchronously upon video loading so they never stall audio initialization:

```python
# ✅ REQUIRED: Asynchronous segment fetch
def load_segments_async(video_id: str, callback):
    def worker():
        try:
            segments = fetch_segments(video_id)
            wx.CallAfter(callback, segments)
        except Exception as e:
            # Non-fatal: playback continues normally without skipping
            pass

    threading.Thread(target=worker, daemon=True).start()
```

### 2. Timecode Polling & Seamless Seek Jump
When observing MPV property `time-pos`, check if current timestamp falls within `[start, end]` of an active segment. If so, seek immediately to `end`:

```python
for seg in self.active_segments:
    if seg.start <= current_time < seg.end:
        # Seek immediately to segment end
        self.player.seek_absolute(seg.end)
        if self.should_announce_skips:
            speech_client.speak(
                _("Skipped {category} segment").format(category=seg.category_name),
                interrupt=True,
            )
        break
```

### 3. Graceful Failure Invariant
SponsorBlock API outages or rate limits must NEVER prevent video playback. If SponsorBlock cannot be reached or returns 404 (no segments found), playback proceeds uninterrupted without errors.

## Quick Reference

| Category Key | Meaning |
| :--- | :--- |
| `sponsor` | Paid promotion, sponsor messages |
| `intro` | Intermission or intro animation |
| `outro` | Endcards, credits |
| `selfpromo` | Unpaid self-promotion, merch, social links |
| `interaction` | Reminders to like, comment, subscribe |
| `music_offtopic` | Non-music section in music videos |

## Implementation Procedures

### Step 1: Adding a New Category Toggle in Settings
1. Add configuration key in `src/settings_handler.py` defaults.
2. In `SettingsDialog`, add checkbox for the category.
3. In `sponsorblock_handler.py`, filter segments based on enabled categories:
   ```python
   enabled_categories = get_enabled_sponsorblock_categories()
   active_segments = [s for s in fetched_segments if s.category in enabled_categories]
   ```

### Step 2: Testing Segment Skipping
Run automated SponsorBlock tests:
```powershell
uv run pytest tests/test_sponsorblock.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Blocking playback on API call | Playback hangs on slow network | Query SponsorBlock in background thread |
| Crashing on 404 No Segments | Most videos don't have sponsors | Catch 404 cleanly and return empty list |
| Infinite seek loop at boundary | If `seg.end` seek lands inside segment | Seek to `seg.end + 0.1` second |
| Loud repeated announcements | Triggers multiple times per second | Mark segment as "already skipped" |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_sponsorblock.py`
- **Lint Check**: Run `uv run ruff check src/sponsorblock_handler.py`
- **Manual Verification**:
  1. Play a sponsored video in HexPlayer.
  2. Verify that playback jumps across the sponsor read automatically.
  3. Verify NVDA / JAWS announces "Skipped sponsor segment".
