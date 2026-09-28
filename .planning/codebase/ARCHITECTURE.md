---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
<!-- refreshed: 2026-09-28 -->

# Architecture

**Analysis Date:** 2026-09-28

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
├──────────────────┬──────────────────┬───────────────────────┤
│    GUI (wx)      │   Media GUI      │      CLI               │
│  `src/gui/`      │ `src/media_player`│   `src/cli/`          │
│  HomeScreen      │  MediaGui        │  app.py / commands.py  │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain / Service Layer                    │
│  youtube_browser/  download_handler/  media_player/          │
│  sponsorblock_handler  cookies_manager  pot_provider_service │
└─────────────────────────────────────────────────────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Platform / Infra Layer                    │
│  paths.py  database.py  settings_handler.py  speech_client   │
│  deno_service.py  runtime_dlls.py  async_utils.py            │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  External: yt-dlp / py-yt · libmpv · Deno (InnerTube) ·      │
│  SQLite (WAL) · SponsorBlock API · Screen readers (Prism)    │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| HomeScreen | Main wx.Frame, app shell, home feed, external URL routing | `src/accessible_youtube_downloader_pro.py` |
| MediaGui | Playback window, transport controls, suggestions, timecodes | `src/media_player/media_gui.py` |
| MpvBackend | ctypes libmpv binding, version-gated loadfile, event loop | `src/media_player/mpv_backend.py` |
| Downloader | yt-dlp download orchestration, progress events | `src/download_handler/downloader.py` |
| YoutubeBrowser / Scraper / SearchHandler | Search, channels, playlists via py-yt | `src/youtube_browser/` |
| CLI app | argparse dispatch, JSON/lang globals | `src/cli/app.py`, `src/cli/commands.py` |
| Settings | INI-backed config with defaults | `src/settings_handler.py` |
| Database | SQLite (WAL) history/favorites with RLock | `src/database.py` |
| Paths | Portable/frozen/XDG path resolution | `src/paths.py` |
| Speech | Screen reader / TTS via Prism | `src/speech_client.py` |
| DenoService | JSON-RPC bridge to Deno InnerTube runtime | `src/deno_service.py` |
| POT / Cookies | Anti-bot PO tokens, cookie auth | `src/pot_provider_service.py`, `src/cookies_manager.py` |

## Pattern Overview

**Overall:** Layered desktop MVC-ish architecture with a flat `src/` module namespace (imports are top-level, not package-qualified for the shell) and feature subpackages (`gui/`, `media_player/`, `youtube_browser/`, `download_handler/`, `cli/`).

**Key Characteristics:**
- Thread-safe GUI: all cross-thread updates routed via `wx.CallAfter` or custom `wx.lib.newevent` events.
- Service singletons (`deno_service`, `pot_service`) imported as module-level instances.
- Dual front-ends (wx GUI and CLI) share the same service/infra layer.
- External subprocess/native bridges (Deno, yt-dlp, libmpv) isolated behind service modules.

## Layers

**Presentation:**
- Purpose: wx dialogs/frames and CLI command handlers.
- Location: `src/gui/`, `src/media_player/media_gui.py`, `src/cli/`
- Depends on: domain + infra layers.

**Domain / Service:**
- Purpose: search, download, playback, SponsorBlock, auth.
- Location: `src/youtube_browser/`, `src/download_handler/`, `src/media_player/`, `src/sponsorblock_handler.py`
- Used by: presentation layer.

**Platform / Infra:**
- Purpose: paths, DB, settings, speech, i18n, async loop, DLL setup, external runtimes.
- Location: `src/paths.py`, `src/database.py`, `src/settings_handler.py`, `src/speech_client.py`, `src/language_handler.py`, `src/async_utils.py`, `src/runtime_dlls.py`, `src/deno_service.py`

## Data Flow

### Primary Request Path (search → play/download)

1. User input in `HomeScreen` / search dialog (`src/gui/search_dialog.py`).
2. `SearchHandler` queries py-yt asynchronously (`src/youtube_browser/search_handler.py`).
3. Results marshalled back to GUI via `wx.CallAfter` (`src/accessible_youtube_downloader_pro.py:665`).
4. Playback: `MediaGui` → `MpvBackend.loadfile` (`src/media_player/mpv_backend.py`); Download: `Downloader` thread emits `ProgressChangedEvent` (`src/download_handler/downloader.py`).

### Startup Flow

1. `runtime_dlls.configure_dll_search_path()` + `configure_linux_display_backend()` before wx import.
2. `utils.configure_py_yt_subprocess()`, translation init, DB init.
3. `wx.App()` → `HomeScreen` → `app.MainLoop()` (`src/accessible_youtube_downloader_pro.py:1072-1102`).

**State Management:**
- Persistent state in SQLite (`src/database.py`) and INI settings (`src/settings_handler.py`).
- Runtime state held on wx frame instances; async loop in `src/async_utils.py`.

## Key Abstractions

**Service singleton:**
- Purpose: single external-runtime bridge instance shared app-wide.
- Examples: `deno_service` (`src/deno_service.py`), `pot_service` (`src/pot_provider_service.py`).

**Custom wx events:**
- Purpose: thread-safe worker→GUI communication.
- Examples: `ProgressChangedEvent`/`EVT_PROGRESS_CHANGED` (`src/download_handler/downloader.py`).

**Emitter (CLI):**
- Purpose: text vs JSON output abstraction.
- Examples: `src/cli/runtime.py`.

## Entry Points

**GUI:**
- Location: `src/accessible_youtube_downloader_pro.py` (`main()` → `wx.App` → `HomeScreen`).

**CLI:**
- Location: `src/hexplayer_cli.py` → `src/cli/app.py` `main()` (argparse dispatch to `cli/commands.py`).

**Native messaging host:**
- Location: `src/native_messaging_host.py` (browser extension bridge).

## Architectural Constraints

- **Threading:** wxPython main-thread only for GUI; background threads and MPV/yt-dlp callbacks must use `wx.CallAfter` (CLAUDE.md invariant #1). Dedicated async loop via `src/async_utils.py`.
- **Global state:** Module-level singletons `deno_service`, `pot_service`; module-level `con` DB connection guarded by `_db_lock` RLock in `src/database.py`.
- **DLL/display init ordering:** `runtime_dlls` calls must run before wx/GTK import (`src/accessible_youtube_downloader_pro.py:9-13`).
- **Path safety:** all paths via `src/paths.py`; respect frozen (`sys._MEIPASS`) and portable modes.

## Anti-Patterns

### Direct GUI access from worker threads

**What happens:** Touching wx widgets from download/search/MPV callbacks.
**Why it's wrong:** Corrupts the wx event loop, crashes with screen readers attached.
**Do this instead:** Route through `wx.CallAfter` or custom events (`src/download_handler/downloader.py`).

### Hardcoded user-facing strings / paths

**What happens:** Literal English text or `%APPDATA%` paths inline.
**Why it's wrong:** Breaks i18n catalog freshness and portability.
**Do this instead:** `from language_handler import _` and `paths.settings_path()` (`src/paths.py`, `src/settings_handler.py`).

## Error Handling

**Strategy:** Broad try/except with logging (`ruff` ignores `BLE001`/`S110` per `pyproject.toml`); DB errors swallowed and logged via `is_valid` decorator.

**Patterns:**
- Module-level `logger = logging.getLogger(__name__)`.
- Custom exceptions like `DownloadCancelled` (`src/download_handler/downloader.py`).

## Cross-Cutting Concerns

**Logging:** stdlib `logging`, per-module loggers.
**Validation:** yt-dlp/py-yt input sanitisation in `src/youtube_url_utils.py`, `src/utils.py`.
**Accessibility:** screen reader announcements via `src/speech_client.py` (`speak`).
**i18n:** `src/language_handler.py` (`_`, `init_translation`), catalogs in `src/languages/`.

---

*Architecture analysis: 2026-09-28*
