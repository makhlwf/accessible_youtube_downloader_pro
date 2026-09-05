---
name: innertube-rpc-bridge
description: >-
  Use when implementing or debugging YouTube search, channel metadata,
  playlist fetching, comments, watch history synchronization, or Deno RPC bridge communication.
---

# Deno & YouTube.js InnerTube RPC Bridge

## Overview

HexPlayer uses an isolated JavaScript subprocess powered by **Deno** and **YouTube.js (Innertube)** (`src/service.js`) communicating with Python (`src/deno_service.py`) via stdio JSON-RPC. This bridge provides resilient YouTube search, channel browsing, comments, recommendations, and authenticated watch history updates without scraping fragile HTML.

## When to Use

- Interacting with YouTube search filters, pagination, or video metadata in `src/youtube_browser/` or `src/deno_service.py`.
- Modifying or debugging `src/service.js` or `src/update_history.js`.
- Fixing Deno subprocess startup failures, pipe communication timeouts, or Windows orphan processes.
- Handling YouTube API schema changes (e.g. comment threads, channel tabs, shorts).
- Passing locale and geolocation parameters (`gl`/`hl`) for accurate regional results.

**When NOT to use:**
- Handling media stream downloads via `yt-dlp` (use `ytdlp-downloader-engine`).
- Managing local SQLite tables (use `sqlite-state-storage`).

## Core Patterns & Invariants

### 1. Stdio JSON-RPC Communication Framing
Messages between Python and Deno are exchanged as single-line JSON objects terminated by `\n` over standard input/output. Each request must include a unique `id`:

```python
# Python Client sending RPC request:
request = {
    "id": self._get_next_id(),
    "method": "search",
    "params": {
        "query": query,
        "location": region_code,  # e.g. 'US', 'EG', 'SA'
        "language": lang_code,  # e.g. 'en', 'ar'
    },
}
self.process.stdin.write(json.dumps(request) + "\n")
self.process.stdin.flush()
```

### 2. Deno Process Lifecycle & Resilience
The Deno process must be spawned with exact security permissions:
`deno run --allow-net --allow-read --allow-env src/service.js`

If the Deno process terminates unexpectedly, `deno_service.py` must detect pipe closure, terminate lingering process handles, and restart the bridge transparently.

### 3. Respecting Regional Parameters (`gl` & `hl`)
Never hardcode YouTube search regions or languages to `US`/`en`. Always query the Windows region:

```python
# ✅ REQUIRED: Resolve system region and user language preference
from utils import get_windows_region
from settings_handler import config_get

region = get_windows_region()  # Returns ISO 3166-1 (e.g. 'GB', 'EG', 'US')
language = config_get("lang") or "en"
```

### 4. Continuation Token Handling for Pagination
InnerTube uses continuation tokens for pagination. Always check for `continuation` before attempting to load more results:

```javascript
// service.js
if (feed.has_continuation) {
    const nextBatch = await feed.getContinuation();
    return { items: formatItems(nextBatch), continuation: nextBatch.continuation };
}
```

## Quick Reference

| Method Name | Parameters | Purpose |
| :--- | :--- | :--- |
| `search` | `{ query, location, language, type }` | Videos, playlists, or channels search |
| `get_video_info` | `{ videoId }` | Video details, description, suggested clips |
| `get_channel` | `{ channelId, tab }` | Channel tabs (Videos, Shorts, Playlists, Live) |
| `get_comments` | `{ videoId, sort_by }` | Top comments or newest comments |
| `update_history` | `{ videoId, cookies }` | Sync watch progress to YouTube account |

## Implementation Procedures

### Step 1: Adding a New RPC Method to `service.js`
1. Define the handler in `service.js`:
   ```javascript
   async function handleGetPlaylist(params) {
       const playlist = await yt.getPlaylist(params.playlistId);
       return {
           title: playlist.info.title,
           videos: playlist.videos.map(v => ({ id: v.id, title: v.title.text }))
       };
   }
   ```
2. Register the method in the JSON-RPC dispatcher map.
3. Add a corresponding Python method in `src/deno_service.py`:
   ```python
   def get_playlist(self, playlist_id: str) -> dict:
       return self.call_method("get_playlist", {"playlistId": playlist_id})
   ```

### Step 2: Testing the JS Bridge Directly
Run Deno's native test runner to verify InnerTube response formats:
```powershell
deno test --allow-net --allow-read src/service_test.js
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Unflushed stdin writes | Request hangs in buffer, Python blocks indefinitely | Always call `stdin.flush()` after write |
| Multiline JSON strings | Breaks newline-delimited message protocol | Use compact single-line JSON |
| Unhandled Deno crash | Future API calls freeze or raise BrokenPipeError | Implement automatic restart logic |
| Hardcoding `location: 'US'` | Ignores user region, breaks localized results | Use `utils.get_windows_region()` |

## Verification & Quality Gates

- **Unit/Integration Tests**: Run `uv run pytest tests/test_search_handler.py tests/test_comments.py tests/test_shorts.py`
- **Lint Check**: Run `uv run ruff check src/deno_service.py`
- **Deno Test**: Run `deno test --allow-net src/service_test.js` (if Deno CLI available)
- **Manual Verification**:
  1. Open Search dialog in HexPlayer (`Ctrl+F`).
  2. Search for regional queries in Arabic and English.
  3. Verify pagination loads subsequent batches smoothly.
