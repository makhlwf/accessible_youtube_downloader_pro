---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# External Integrations

**Analysis Date:** 2026-09-28

## APIs & External Services

**YouTube (data/metadata):**
- InnerTube via `youtubei.js@18.1.0` - Runs inside a bundled Deno subprocess. Bridge: `src/deno_service.py` (JSON-RPC over stdio, `deno run --allow-all --config`), service script `src/service.js`.
- YouTube search - `py-yt-search==0.8.0` and HTML scraping via `beautifulsoup4` in `src/youtube_browser/scraper.py`, `src/youtube_browser/search_handler.py`.
- Media download/extraction - yt-dlp (runtime-managed `yt_dlp.zip`, not a pinned dep) invoked from `src/download_handler/downloader.py`, `src/cookies_manager.py`, `src/utils.py`.

**SponsorBlock:**
- `sponsorblock-py` client - Segment skip/mute data. `src/sponsorblock_handler.py`.
  - API: `https://sponsor.ajay.app` (`DEFAULT_API_URL`).
  - Categories: sponsor, selfpromo, interaction, intro, outro, preview, hook, filler, music_offtopic.

**PO Token / Anti-Bot Provider:**
- `bgutil-ytdlp-pot-provider-rs` - Downloaded from GitHub releases (`jim60105/bgutil-ytdlp-pot-provider-rs`), managed in `src/pot_provider_service.py`.
  - Downloads `bgutil-pot-windows-x86_64.exe`; integrity enforced via `PINNED_RELEASE_HASHES` (SHA-256) and `EXPECTED_URL_PREFIX`.
  - Installs `yt_dlp_plugins` for POT provisioning.

**GitHub / npm (update & version checks):**
- yt-dlp latest: `https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp` (`src/utils.py`).
- Generic release lookup: `https://api.github.com/repos/{repo}/releases/latest` (`src/utils.py`, `src/pot_provider_service.py`).
- npm registry: `https://registry.npmjs.org/{package}/latest` for `youtubei.js` version checks (`src/utils.py`).
- App self-update feed: `update.json` / `update_info.json` served from GitHub releases (`makhlwf/accessible_youtube_downloader_pro`).

## Data Storage

**Databases:**
- SQLite - Local application state (history, favorites, settings). `src/database.py`.
  - Connection: `paths.db_path`; PRAGMA `journal_mode=WAL`, `synchronous=NORMAL`; thread-safe via `RLock` + `check_same_thread=False`.
  - Client: stdlib `sqlite3`.

**File Storage:**
- Local filesystem only. Paths resolved via `src/paths.py` (settings dir, downloads dir, portable mode). Downloaded media, `yt_dlp.zip`, POT provider binaries, and DLLs stored under resolved app paths.

**Caching:**
- youtubei.js runtime cache (refreshable via "refresh youtubei cache" action, `src/utils.py`).

## Authentication & Identity

**Auth Provider:**
- No first-party account system. YouTube auth is via browser cookie extraction.
  - `src/cookies_manager.py` extracts cookies via yt-dlp `extract_cookies_from_browser`.
  - Supported browsers: Firefox, Chrome, Edge, Brave, Opera, Vivaldi, Chromium (`SUPPORTED_BROWSERS_MAP`).
  - Linux keyring access via `secretstorage` (`SecretStorage`) for encrypted cookie stores.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/telemetry SDK detected). See `PRIVACY_POLICY.md`.

**Logs:**
- Python stdlib `logging` throughout (`logging.getLogger(__name__)` per module).

## CI/CD & Deployment

**Hosting:**
- GitHub Releases (Windows `.exe`, Linux `.tar.xz`/`.deb`/`.rpm`), winget distribution.

**CI Pipeline:**
- GitHub Actions (`.github/workflows/`): `build-artifacts.yml`, `release.yml`, `beta.yml`, `tests.yml`, `lint.yml`, `translations_check.yml`, `winget.yml`, `labeler.yml`, `stale.yml`, `automergedrpbotprs.yml`.

## Environment Configuration

**Required env vars:**
- None mandatory. `PATH` augmented at runtime for bundled binaries (`src/deno_service.py`). Linux: `XDG_CONFIG_HOME` respected for browser/cookie discovery.

**Secrets location:**
- No secrets committed. Browser cookies read on demand; Linux secrets via system keyring (`secretstorage`). No `.env` present.

## Webhooks & Callbacks

**Incoming:**
- Local IPC socket for browser-extension launch requests: TCP `127.0.0.1:57280` (`src/native_messaging_host.py`, `IPC_HOST`/`IPC_PORT`).
- Chrome/Firefox Native Messaging host (length-prefixed stdio JSON) - `src/native_messaging_host.py`, registered via `src/browser_extension_manager.py`.

**Outgoing:**
- None (no outbound webhooks). Browser extension (MV3, `src/browser_extension/manifest.json`) forwards YouTube links to the native host; host permissions `*://*.youtube.com/*`, `*://*.google.com/*`.

---

*Integration audit: 2026-09-28*
