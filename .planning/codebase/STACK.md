---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# Technology Stack

**Analysis Date:** 2026-09-28

## Languages

**Primary:**
- Python `>=3.14` (pinned to 3.14.7 via `.python-version`) - All application, GUI, CLI, and service code under `src/`.

**Secondary:**
- JavaScript / TypeScript (Deno runtime) - InnerTube RPC bridge in `src/service.js`, `src/service_test.js`, `src/update_history.js`, configured by `src/deno.json`.
- JavaScript (Browser WebExtension, MV3) - `src/browser_extension/*.js` (background service worker, content scripts, options).

## Runtime

**Environment:**
- CPython 3.14 (Windows primary target, Linux supported per `pyproject.toml` description).
- Bundled Deno runtime (`src/deno.exe`) executes the `youtubei.js` service (`src/deno_service.py`).
- Bundled MPV (`src/libmpv-2.dll`) and FFmpeg binaries (`src/ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`, `avcodec-60.dll`, etc.) for media playback/transcoding.

**Package Manager:**
- `uv` (Astral) - project/venv manager. `[tool.uv] package = false`.
- Lockfile: `uv.lock` present (~156 KB).
- Deno deps locked via `src/deno.lock`; npm registry consulted for `youtubei.js` version checks.

## Frameworks

**Core:**
- `wxpython==4.3.1` - Desktop GUI toolkit (all dialogs under `src/gui/`, main window `src/accessible_youtube_downloader_pro.py`).

**Testing:**
- `pytest>=9.0.2,<10` - Test runner. Config in `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `pythonpath=["src"]`).
- `pytest-asyncio>=1.3.0,<2` - Async test support.

**Build/Dev:**
- `ruff==0.16.8` - Lint + format. `target-version = "py314"`, ignores `BLE001`, `S110`.
- `babel==2.18.0` - i18n string extraction (`babel.cfg`, `messages.pot`).
- `pre-commit>=4.6.2,<5` - Git hooks (`.pre-commit-config.yaml`).
- `pyinstaller>=6.22.0,<7` (build group) - Frozen executable packaging (`HexPlayer.spec`, `scripts/build.py`).
- `just` - Task runner (`justfile`: run, preflight, lint, test, translations, build, package).

## Key Dependencies

**Critical:**
- `prismatoid>=0.17.3` (`prism`) - Screen reader / TTS backend abstraction; core accessibility layer (`src/speech_client.py`).
- `wxpython==4.3.1` - GUI.
- `py-yt-search==0.8.0` - YouTube search.
- `sponsorblock-py>=1.0.0` (`sponsorblock`) - SponsorBlock segment lookup (`src/sponsorblock_handler.py`).
- yt-dlp - NOT a pinned dependency; downloaded/managed at runtime as `yt_dlp.zip` (`src/paths.py`, `src/utils.py`) from GitHub releases.

**Infrastructure:**
- `httpx==0.28.1` - HTTP client.
- `requests==2.34.2` - HTTP (POT provider downloads, GitHub/npm version checks in `src/utils.py`, `src/pot_provider_service.py`).
- `beautifulsoup4==4.15.0` - HTML scraping (`src/youtube_browser/scraper.py`).
- `pyperclip==1.11.0` - Clipboard URL monitoring.
- `secretstorage>=3.3.3,<4` (Linux only) - Secret/keyring access for cookies.

## Configuration

**Environment:**
- Settings persisted via `src/settings_handler.py` + `src/database.py` (SQLite, WAL mode).
- Paths resolved through `src/paths.py` (`settings_path`, `db_path`, portable-mode aware). No hardcoded `%APPDATA%`.
- No `.env` file in repo; runtime config lives in JSON settings + SQLite DB under the resolved settings path.

**Build:**
- `pyproject.toml` - project metadata + dependency groups.
- `HexPlayer.spec` - PyInstaller build spec.
- `packaging/windows/inno.iss` - Inno Setup installer; `packaging/linux/` for deb/rpm/tar.xz.
- `babel.cfg` - i18n extraction (`[python: src/**.py]`, utf-8).
- `src/deno.json` / `src/deno.lock` - Deno import map (`youtubei.js@18.1.0`).

## Platform Requirements

**Development:**
- Python 3.14, `uv`, Deno (bundled), Node/npm registry reachable for version checks, `just` (optional), Inno Setup (`iscc`) for Windows installer.

**Production:**
- Windows: single-file `HexPlayer.exe` (PyInstaller + Inno installer), also `winget` manifest workflow.
- Linux: `.tar.xz`, `.deb`, `.rpm` artifacts (see `update.json`).

---

*Stack analysis: 2026-09-28*
