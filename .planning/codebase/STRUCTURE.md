---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# Codebase Structure

**Analysis Date:** 2026-09-28

## Directory Layout

```
accessible_youtube_downloader_pro/
├── src/                         # All application source (pythonpath root)
│   ├── accessible_youtube_downloader_pro.py  # GUI entry point (HomeScreen, main)
│   ├── hexplayer_cli.py         # CLI entry point
│   ├── application.py           # App constants (name, version, urls)
│   ├── paths.py                 # Path resolution (portable/frozen/XDG)
│   ├── database.py              # SQLite (WAL) state store
│   ├── settings_handler.py      # INI settings with defaults
│   ├── speech_client.py         # Screen reader / TTS (Prism)
│   ├── language_handler.py      # i18n (_, init_translation)
│   ├── async_utils.py           # Background asyncio loop
│   ├── runtime_dlls.py          # DLL search path + display backend setup
│   ├── deno_service.py          # Deno InnerTube JSON-RPC bridge
│   ├── pot_provider_service.py  # PO token anti-bot service
│   ├── cookies_manager.py       # Cookie auth
│   ├── sponsorblock_handler.py  # SponsorBlock segments
│   ├── native_messaging_host.py # Browser extension host
│   ├── gui/                     # wx dialogs and frames
│   ├── media_player/            # MPV backend, MediaGui, equalizer, timecodes
│   ├── download_handler/        # yt-dlp downloader
│   ├── youtube_browser/         # search, scraper, browser, channels/playlists
│   ├── cli/                     # argparse app + commands
│   ├── languages/{ar,en}/       # gettext catalogs
│   ├── docs/{ar,en}/            # bundled documentation
│   ├── eq_presets/              # equalizer preset JSON
│   ├── include/mpv/             # bundled mpv runtime
│   └── browser_extension/       # extension assets
├── tests/                       # pytest suite (co-located conftest.py)
├── scripts/                     # agent_preflight.py, build.py, check_translations.py
├── packaging/{linux,windows}/   # platform packaging + validators
├── .github/workflows/           # CI (tests, lint, release, beta, winget...)
├── .agents/skills/              # subsystem runbooks (SKILL.md)
├── HexPlayer.spec               # PyInstaller spec
├── pyproject.toml               # uv project, deps, ruff/pytest config
├── babel.cfg / messages.pot     # i18n extraction
└── uv.lock
```

## Directory Purposes

**`src/gui/`:**
- Purpose: all wx dialog/frame classes (settings, search, history, favorites, download, equalizer, tray, etc.).
- Key files: `settings_dialog.py`, `comments_dialog.py`, `channel_dialog.py`, `custom_controls.py`, `tray_icon.py`.

**`src/media_player/`:**
- Purpose: playback subsystem.
- Key files: `media_gui.py` (2639 lines), `mpv_backend.py`, `player.py`, `equalizer.py`, `suggestions_service.py`, `timecodes.py`.

**`src/youtube_browser/`:**
- Purpose: content discovery via py-yt.
- Key files: `search_handler.py`, `browser.py`, `scraper.py`.

**`src/cli/`:**
- Purpose: command-line front-end.
- Key files: `app.py`, `commands.py`, `runtime.py`, `deps.py`.

## Key File Locations

**Entry Points:**
- `src/accessible_youtube_downloader_pro.py`: GUI (`main`, `HomeScreen`).
- `src/hexplayer_cli.py` → `src/cli/app.py`: CLI.
- `src/native_messaging_host.py`: browser extension bridge.

**Configuration:**
- `pyproject.toml`: deps, ruff (py314 target), pytest (`pythonpath=["src"]`).
- `src/settings_handler.py`: runtime user settings + defaults.
- `babel.cfg`, `messages.pot`: translations.

**Core Logic:**
- `src/utils.py` (3418 lines): shared helpers, subprocess config.
- `src/download_handler/downloader.py`: download engine.

**Testing:**
- `tests/`: ~40+ `test_*.py`, `conftest.py` fixtures.

## Naming Conventions

**Files:**
- snake_case modules: `settings_handler.py`, `mpv_backend.py`.
- Tests prefixed `test_`: `test_downloader.py`.
- Feature dialogs suffixed `_dialog.py` in `gui/`.

**Classes:**
- PascalCase: `HomeScreen`, `MediaGui`, `MpvBackend`, `DenoService`.

**Directories:**
- lowercase feature subpackages: `media_player`, `youtube_browser`.

## Where to Add New Code

**New Feature:**
- Primary code: relevant `src/` subpackage (`gui/`, `media_player/`, `youtube_browser/`, `download_handler/`).
- Tests: `tests/test_<feature>.py`.

**New GUI dialog:**
- Implementation: `src/gui/<name>_dialog.py`; ensure accessible labels, TAB traversal, `wx.CallAfter` for threaded updates.

**New CLI command:**
- Handler in `src/cli/commands.py`, wired into parser in `src/cli/app.py`.

**Utilities:**
- Shared helpers: `src/utils.py`; path helpers only in `src/paths.py`.

**User-facing strings:**
- Wrap with `_()` from `src/language_handler.py`; re-extract to `messages.pot`.

## Special Directories

**`src/include/mpv/`:**
- Purpose: bundled libmpv runtime. Generated/vendored: Yes. Committed: Yes.

**`build/`, `dist/`:**
- Purpose: PyInstaller output. Generated: Yes. Committed: No (gitignored).

**`src/languages/{ar,en}/`:**
- Purpose: compiled gettext catalogs. Committed: Yes.

---

*Structure analysis: 2026-09-28*
