---
name: innertube-rpc-bridge
description: >-
  Use when implementing or debugging YouTube search, channel metadata,
  playlist fetching, comments, watch history synchronization, or JavaScript RPC bridge communication.
---

# JavaScript & YouTube.js InnerTube RPC Bridge

## Overview

HexPlayer uses an isolated JavaScript subprocess executing **YouTube.js (Innertube)** (`src/service.js`) communicating with Python (`src/deno_service.py`) via stdio JSON-RPC. This bridge provides resilient YouTube search, channel browsing, comments, recommendations, and authenticated watch history updates without scraping fragile HTML.

The bridge operates on a **dual-runtime architecture**:
- **Primary Runtime:** A 6.18 MB standalone native binary (`src/youtube_service.exe`) powered by QuickJS-ng + libuv + curl (txiki.js).
- **Fallback Runtime:** Legacy Deno (`deno.exe`) executing `src/service.js` directly with on-the-fly npm package caching.

## When to Use

- Interacting with YouTube search filters, pagination, or video metadata in `src/youtube_browser/` or `src/deno_service.py`.
- Modifying or debugging `src/service.js`, `src/polyfill.js`, or `scripts/build_youtube_service.py`.
- Fixing JavaScript subprocess startup failures, pipe communication timeouts, or Windows orphan processes.
- Compiling or updating the standalone `youtube_service.exe` binary.
- Handling YouTube API schema changes (e.g. comment threads, channel tabs, shorts).
- Passing locale and geolocation parameters (`gl`/`hl`) for accurate regional results.

**When NOT to use:**
- Handling media stream downloads via `yt-dlp` (use `ytdlp-downloader-engine`).
- Managing local SQLite tables (use `sqlite-state-storage`).

## Core Patterns & Invariants

### 1. Stdio JSON-RPC Communication Framing
Messages between Python and the JavaScript runtime are exchanged as single-line JSON objects terminated by `\n` over standard input/output. Each request must include a unique `id`:

```python
# Python Client sending RPC request:
request = {
    "id": self._get_next_id(),
    "command": "search",
    "params": {
        "query": query,
        "location": region_code,  # e.g. 'US', 'EG', 'SA'
        "language": lang_code,  # e.g. 'en', 'ar'
    },
}
self.process.stdin.write(json.dumps(request) + "\n")
self.process.stdin.flush()
```

### 2. Standalone Service & Deno Fallback Priority
`src/deno_service.py` checks `paths.get_youtube_service_path()` first:
- If `youtube_service.exe` exists, spawn `[youtube_service_path]`.
- Otherwise, fall back to `[deno_path, "run", "--allow-net", "--allow-read", "--allow-env", service_script]`.

### 3. Polyfill Invariants for QuickJS & txiki.js
When bundling `service.js` with `tjs bundle` for QuickJS:
- **Timezone Shim:** QuickJS lacks full ICU timezone data; `src/polyfill.js` shims `Intl.DateTimeFormat`.
- **URL Stringification:** Native C `fetch()` in txiki.js crashes on `URL` instances; `src/polyfill.js` forces `input.toString()`.
- **Injection Order:** Polyfills MUST be injected with `--inject:polyfill.js` so they evaluate before ES module imports hoist.

### 4. Respecting Regional Parameters (`gl` & `hl`)
Never hardcode YouTube search regions or languages to `US`/`en`. Always query the Windows region:

```python
from utils import get_windows_region
from settings_handler import config_get

region = get_windows_region()  # Returns ISO 3166-1 (e.g. 'GB', 'EG', 'US')
language = config_get("lang") or "en"
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
1. Define the handler case in `src/service.js`:
   ```javascript
   case "get_playlist": {
       const playlist = await yt.getPlaylist(params.playlistId);
       return {
           title: playlist.info.title,
           videos: playlist.videos.map(v => ({ id: v.id, title: v.title.text }))
       };
   }
   ```
2. Add a corresponding Python method in `src/deno_service.py`:
   ```python
   def get_playlist(self, playlist_id: str) -> dict:
       return self.send_command("get_playlist", {"playlistId": playlist_id})
   ```
3. Recompile the standalone binary:
   ```bash
   uv run python scripts/build_youtube_service.py
   ```

### Step 2: Compiling and Testing the Standalone Service
Run the automated build script which bundles dependencies, injects polyfills, compiles the single binary, and verifies via JSON-RPC:
```powershell
uv run python scripts/build_youtube_service.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Modifying `service.js` without recompiling | Standalone binary runs outdated code | Run `build_youtube_service.py` after editing `service.js` |
| Omitting `--inject:polyfill.js` | ES module hoisting evaluates imports before shims | Always use `--inject:polyfill.js` in esbuild |
| Unflushed stdin writes | Request hangs in buffer, Python blocks indefinitely | Always call `stdin.flush()` after write |
| Multiline JSON strings | Breaks newline-delimited message protocol | Use compact single-line JSON |
| Unhandled process crash | Future API calls freeze or raise BrokenPipeError | Implement automatic restart logic in `deno_service.py` |
| Hardcoding `location: 'US'` | Ignores user region, breaks localized results | Use `utils.get_windows_region()` |

## Verification & Quality Gates

- **Preflight Verification**: Run `uv run python scripts/agent_preflight.py`.
- **Standalone Service Test**: Run `uv run pytest tests/test_youtube_service.py`.
- **CLI Diagnostics**: Run `src\youtube_service.exe --version` and `src\youtube_service.exe --help`.
- **Manual Verification**:
  1. Open Search dialog in HexPlayer (`Ctrl+F`).
  2. Search for regional queries in Arabic and English.
  3. Verify pagination loads subsequent batches smoothly.
