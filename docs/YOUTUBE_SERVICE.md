# YouTube Service & InnerTube Bridge Guide

This document is the definitive guide to HexPlayer's YouTube InnerTube service architecture, explaining how the lightweight JavaScript runtime operates, how to build and update it, how to add new YouTube.js features, and how the dual-runtime fallback works.

---

## 1. Overview & Architecture

HexPlayer interfaces with YouTube using **YouTube.js (Innertube)**, an open-source TypeScript/JavaScript client that communicates directly with YouTube's internal APIs (InnerTube). This allows HexPlayer to perform fast, robust searches, retrieve comments, load channel tabs, and extract timestamped chapters without scraping brittle web HTML.

### Dual-Runtime Design

To run YouTube.js on desktop operating systems, HexPlayer supports a dual-runtime architecture:

```
                      ┌───────────────────────────────────────┐
                      │    HexPlayer Python Application       │
                      │       (src/deno_service.py)           │
                      └──────────────────┬────────────────────┘
                                         │
                         Stdio JSON-RPC (newline-delimited)
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
                 ▼                                               ▼
      [PRIMARY RUNTIME]                               [FALLBACK RUNTIME]
    src/youtube_service.exe                             deno.exe + src/service.js
  * 6.18 MB standalone binary                         * ~94.5 MB Deno engine
  * Powered by QuickJS-ng + txiki.js                  * Dynamically caches npm:youtubei.js
  * Zero runtime dependencies                         * Used if youtube_service.exe absent
  * Inno Setup bundle: ~1.8 MB compressed
```

1. **Primary: Standalone Native Binary (`youtube_service.exe`)**:
   - A single **6.18 MB executable** bundling the JS engine (QuickJS-ng + libuv + curl via [txiki.js](https://github.com/saghul/txiki.js)), polyfills, `service.js`, and `youtubei.js`.
   - Achieves a **93.5% reduction** in disk space compared to Deno (6.18 MB vs 94.55 MB).
   - Has zero external dependencies: no Node.js, npm, or Deno required at runtime on the user's computer.
   - Compresses down to ~1.8 MB inside the Inno Setup Windows installer.

2. **Fallback: Legacy Deno Engine (`deno.exe`)**:
   - If `youtube_service.exe` is absent or deleted, `src/deno_service.py` automatically falls back to `deno.exe src/service.js`.
   - The user or developer experiences zero downtime or breakage.

---

## 2. How People Build the Executable

The build process is fully automated via [`scripts/build_youtube_service.py`](file:///C:/accessible_youtube_downloader_pro/scripts/build_youtube_service.py).

### Prerequisites

To build `youtube_service.exe`, your development machine needs:
1. **Python 3.11+** with `uv` (or pip) installed.
2. **Node.js & npm** (Node.js 18+ recommended): npm is used to fetch and resolve `youtubei.js` packages; `tjs bundle` utilizes Node/npm module resolution.
3. **Internet connection**: required on the first build to download the txiki.js runtime and npm packages.

### Building `youtube_service.exe`

From the repository root, run:

```bash
uv run python scripts/build_youtube_service.py
```

### What the Build Script Does

The build script performs 5 automated stages:
1. **Stage 1 — Runtime Acquisition**: Downloads `txiki.js` (v24.11.0 Windows x64 binary) from GitHub releases to `build/js_service/tjs.exe` (cached for subsequent builds).
2. **Stage 2 — Package Installation**: Runs `npm install youtubei.js@latest` in `build/js_service/` to obtain the latest InnerTube library.
3. **Stage 3 — Bundling & Polyfill Injection**:
   - Stages `src/service.js` and `src/polyfill.js` adjacent to `node_modules/`.
   - Invokes `tjs.exe bundle --inject:polyfill.js service.js -o service.bundle.js`.
   - `tjs bundle` uses embedded `esbuild` to package all dependencies into a single, self-contained ES module (`service.bundle.js`, ~1.3 MB).
   - Injects polyfills *before* module evaluation (critical for `Intl` and `fetch`).
4. **Stage 4 — Native Binary Compilation**:
   - Invokes `tjs.exe compile service.bundle.js src/youtube_service.exe`.
   - Produces a single native PE binary (`src/youtube_service.exe`, ~6.18 MB).
5. **Stage 5 — Health Verification**:
   - Spawns the newly compiled binary and executes a JSON-RPC ping to verify that QuickJS, libuv, curl, and InnerTube communicate successfully.

### Command-Line Options

```bash
# Build to a custom output path
uv run python scripts/build_youtube_service.py --output dist/youtube_service.exe

# Skip the post-compilation JSON-RPC handshake verification
uv run python scripts/build_youtube_service.py --no-verify
```

### Packaging into HexPlayer Releases

To compile the entire HexPlayer application including the standalone service:

```bash
uv run python scripts/build.py --build-youtube-service
```

This compiles `youtube_service.exe` first, and then runs PyInstaller (`HexPlayer.spec`) which automatically bundles `youtube_service.exe` into `dist/HexPlayer/_internal/`.

---

## 3. How YouTube.js Updating Works

YouTube frequently modifies its internal InnerTube API and player signatures. To keep HexPlayer running without requiring a full application reinstallation, updating works through two mechanisms:

### A. End-User Field Updates (Production)

End users running HexPlayer do not need Node.js, npm, or Deno installed to update YouTube.js:

1. **Automated GitHub Release Asset**:
   - Updated builds of `youtube_service.exe` are published to GitHub Releases under `makhlwf/accessible_youtube_downloader_pro`.
2. **GUI Update (`src/utils.py`)**:
   - Users can trigger update checks from the menu (`Help > Check for Updates` or `Tools > Dependencies`).
   - `utils.update_youtube_service()` queries the latest release on GitHub, downloads the 6.18 MB binary via `UpdateDialog`, and saves it to:
     - Non-portable mode: `%APPDATA%\HexPlayer\youtube_service.exe`
     - Portable mode: `<AppFolder>\youtube_service.exe`
   - Because [`src/paths.py`](file:///C:/accessible_youtube_downloader_pro/src/paths.py) checks `%APPDATA%\HexPlayer\` *before* the application directory, the newly downloaded binary immediately overrides the older bundled version without requiring administrator privileges.
3. **CLI Update (`src/cli/deps.py`)**:
   - Terminal users can run:
     ```bash
     hexplayer-cli deps update --youtubei
     ```
   - If `youtube_service.exe` is present, it downloads and replaces the standalone binary headlessly.
   - If Deno is used, it runs `deno cache --reload=npm:youtubei.js`.

### B. Developer / CI Build-Time Updates

Whenever `youtubei.js` publishes a new release on npm:
1. Run:
   ```bash
   uv run python scripts/build_youtube_service.py
   ```
2. The script runs `npm install youtubei.js@latest`, re-bundles, compiles, and tests the updated `src/youtube_service.exe`.
3. Commit and push the updated binary or upload it as a release asset.

---

## 4. How to Add and Use Other YouTube.js Features

The entire YouTube.js library is available within `src/service.js`. You can expose any YouTube.js capability to Python in three simple steps.

### Step 1: Add the Command to `src/service.js`

In [`src/service.js`](file:///C:/accessible_youtube_downloader_pro/src/service.js), locate the `handleCommand` dispatcher function. Add your new command `case`:

```javascript
case "get_channel_playlists": {
    // 1. Get channel instance using YouTube.js
    const channel = await yt.getChannel(params.channelId);
    
    // 2. Fetch the 'playlists' tab
    const playlistsTab = await channel.getPlaylists();
    
    // 3. Format results into clean JSON for Python
    const items = playlistsTab.playlists.map(pl => ({
        id: pl.id,
        title: pl.title?.text || "",
        video_count: pl.video_count?.text || "0",
        thumbnails: pl.thumbnails
    }));
    
    return {
        playlists: items,
        has_continuation: playlistsTab.has_continuation
    };
}
```

### Step 2: Add the Python Wrapper to `src/deno_service.py`

In [`src/deno_service.py`](file:///C:/accessible_youtube_downloader_pro/src/deno_service.py), add a method to `DenoService`:

```python
def get_channel_playlists(self, channel_id: str) -> dict:
    """Fetch playlists belonging to a YouTube channel via InnerTube."""
    return self.send_command("get_channel_playlists", {"channelId": channel_id})
```

### Step 3: Recompile the Standalone Service

Rebuild the binary to incorporate the new code:

```bash
uv run python scripts/build_youtube_service.py
```

### Examples of Features You Can Add

- **Transcripts / Subtitles**:
  ```javascript
  const info = await yt.getInfo(params.videoId);
  const transcript = await info.getTranscript();
  return transcript.transcript.content.body.initial_segments.map(s => ({
      text: s.snippet.text,
      start_ms: s.start_ms,
      end_ms: s.end_ms
  }));
  ```
- **Live Chat Stream**:
  ```javascript
  const liveChat = await yt.getLiveChat(params.videoId);
  // Listen for liveChat events or poll messages
  ```
- **Playlist Management** (requires `cookiesPath`):
  ```javascript
  await yt.playlist.create(params.title, [params.videoId]);
  ```
- **YouTube Music API**:
  ```javascript
  const music = yt.music;
  const album = await music.getAlbum(params.browseId);
  return album;
  ```

---

## 5. Polyfills & QuickJS Invariants

QuickJS-ng is an ultra-compact ECMAScript engine, but standard QuickJS lacks browser Web APIs and full ICU locale databases. [`src/polyfill.js`](file:///C:/accessible_youtube_downloader_pro/src/polyfill.js) bridges these differences:

1. **`Intl.DateTimeFormat` Polyfill**:
   - QuickJS does not bundle full ICU timezone data. `youtubei.js` calls `Intl.DateTimeFormat(undefined, { timeZone: ... })` during initialization.
   - `polyfill.js` shims `Intl.DateTimeFormat` so timezone queries fall back gracefully without throwing `RangeError: unsupported time zone`.

2. **`fetch(input, init)` Polyfill**:
   - txiki.js provides native `fetch()` implemented via `libcurl`.
   - However, txiki.js `fetch()` expects `input` to be a primitive string. If passed a WHATWG `URL` object (`fetch(new URL(...))`), txiki.js throws `TypeError: Invalid URL`.
   - `polyfill.js` wraps `globalThis.fetch` to ensure `input = input.toString()` is called before passing it to native C code.

3. **ESBuild Hoisting Rule**:
   - ES module `import` statements are hoisted to the top of the bundle.
   - Placing polyfills at the top of `service.js` is ineffective because `import { Innertube } from 'youtubei.js'` evaluates *before* top-level statements.
   - Therefore, `scripts/build_youtube_service.py` builds with:
     ```
     tjs bundle --inject:polyfill.js service.js -o service.bundle.js
     ```
   - The `--inject` flag guarantees that `polyfill.js` executes prior to any module body.

---

## 6. Diagnostic & CLI Commands

`youtube_service.exe` includes CLI flags to inspect the binary without opening a persistent stdio channel:

```bash
# Print service version
src\youtube_service.exe --version
# Output: youtube_service 1.0.0

# Print usage instructions
src\youtube_service.exe --help
```

### Manual Interactive Testing

You can test RPC commands directly via standard input from PowerShell:

```powershell
echo '{"id": 1, "command": "get_video_likes", "params": {"videoId": "dQw4w9WgXcQ"}}' | src\youtube_service.exe
```

Expected output:
```json
{"id":1,"result":{"likes":17452102,"rating":null,"is_liked":false,"is_disliked":false}}
```
