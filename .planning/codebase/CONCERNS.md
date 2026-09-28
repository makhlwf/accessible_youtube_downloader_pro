---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# Codebase Concerns

**Analysis Date:** 2026-09-28

## Tech Debt

**`src/utils.py` god module:**
- Issue: Single 3,418-line module with 138 top-level defs/classes mixing unrelated concerns — yt-dlp loading, subtitle parsing (json3/vtt/xml), Deno/InnerTube version management, GitHub/npm release checks, Windows region detection, audio-track language matching, and an `InfoCache`.
- Files: `src/utils.py`
- Impact: High coupling, hard to test in isolation, merge-conflict magnet, unclear ownership. Any subsystem change routes through this file.
- Fix approach: Split into focused modules (`subtitles.py`, `ytdlp_loader.py`, `deno_versions.py`, `region.py`, `info_cache.py`) under a `utils/` package, preserving public import names via a shim.

**Blind exception handling suppressed by lint config:**
- Issue: `pyproject.toml` sets `[tool.ruff.lint] ignore = ["BLE001", "S110"]`, deliberately silencing "blind except" and "try-except-pass" warnings. Repository has 206 `except Exception`/bare handlers in `src/`, of which 67 are `except Exception: pass`.
- Files: `pyproject.toml`; heavy clusters in `src/accessible_youtube_downloader_pro.py` (lines 86-97, 114-144, 217), `src/utils.py`.
- Impact: Real failures (thread crashes, corrupt state, screen-reader announcement failures) are swallowed silently, undermining the "announce errors immediately" a11y invariant. Hard to diagnose field bugs.
- Fix approach: Narrow handlers to expected exception types; at minimum log at `warning`/`error` in each swallow site. Re-enable BLE001/S110 incrementally and audit remaining suppressions with `# noqa` justifications.

**Leftover DEBUG log line in production path:**
- Issue: `logger.info(f"DEBUG: Checking for playlist_id. URL: {url_full}. Detected ID: {playlist_id}")` — a debug string shipped at INFO level.
- Files: `src/utils.py:1963`
- Impact: Noisy logs, leaks full URLs (may contain playlist/mix identifiers) into log files at normal verbosity.
- Fix approach: Downgrade to `logger.debug` and remove the "DEBUG:" prefix, or delete.

## Known Bugs

**Embedded video on Wayland (open regression):**
- Symptoms: Embedded mpv video output does not render correctly under Wayland (Linux).
- Files: `src/media_player/mpv_backend.py`, `src/media_player/media_gui.py`
- Trigger: Running with embedded video on a Wayland session. (The related `loadfile` 5-arg shape rejection by mpv 0.37 was fixed in PR #82 via version-gating in `_load_current`; Wayland embedding remains open per project memory.)
- Workaround: None documented; windowed/detached output may behave differently.

## Security Considerations

**Runtime yt-dlp loading via `sys.path.insert` + `import`:**
- Risk: `load_yt_dlp()` inserts a filesystem path (`paths.yt_dlp_path`, potentially a downloaded/updated zip) into `sys.path` and imports it at module load time (`load_yt_dlp()` called at import, line 656). Code from a self-updating archive executes with full app privileges.
- Files: `src/utils.py:619-656`, `src/utils.py:936` (`download_yt_dlp`), `1213` (`update_yt_dlp`)
- Current mitigation: `_loaded_from_path` verifies the module resolved from the expected path; zip validity is checked via `zipfile.is_zipfile`; corrupt archives are discarded.
- Recommendations: Verify archive integrity/signature before adding to `sys.path`; fetch updates over HTTPS from a pinned source only; avoid leaving the injected path on `sys.path` after load.

**Subprocess launch of downloaded/updated binaries:**
- Risk: `subprocess.Popen` launches external processes including the update installer (`src/gui/update_dialog.py:240` runs a downloaded installer with `/SILENT`) and the Deno runtime (`src/deno_service.py:42`).
- Files: `src/gui/update_dialog.py:240`, `src/deno_service.py:42`, `src/native_messaging_host.py`, `src/accessible_youtube_downloader_pro.py:200-206`
- Current mitigation: No `shell=True` anywhere (0 occurrences) — good; `CREATE_NO_WINDOW` used to avoid console flashes.
- Recommendations: Verify installer authenticity (signature/hash) before executing the silent installer; validate the update source is the trusted GitHub release.

**Cookie / credential material on disk:**
- Risk: Cookie and auth handling across `src/cookies_manager.py`, `src/download_handler/downloader.py`, and cookie-path plumbing in `src/utils.py`.
- Files: `src/cookies_manager.py`, `src/utils.py` (`cookies_path` usage around line 1968)
- Current mitigation: Linux uses `secretstorage` for secrets (pyproject dependency).
- Recommendations: Ensure cookie files use restrictive permissions; avoid logging cookie paths alongside URLs (see DEBUG line above).

## Performance Bottlenecks

**Module-load-time work in `src/utils.py`:**
- Problem: `load_yt_dlp()` executes at import time (line 656), performing filesystem probing, zip validation, and a potentially heavy `import yt_dlp`. Importing `utils` blocks on this.
- Files: `src/utils.py:656`
- Cause: Eager side-effectful import.
- Improvement path: Make yt-dlp loading lazy (first-use) so app/CLI startup and test collection are not blocked.

## Fragile Areas

**Module-level mutable globals / singletons:**
- Files: `src/database.py:104` (`global con`), `src/settings_handler.py:92,125,184,196` (`_config`, `_cache`, `_save_timer`), `src/media_player/mpv_backend.py:177,897` (`_mpv_lib`, `_audio_devices_cache`), `src/async_utils.py:11` (`_async_loop`), `src/cli/runtime.py:23` (`_BOOTSTRAPPED`)
- Why fragile: Shared mutable state accessed from GUI and background threads risks races; a debounced `_save_timer` in settings can drop or overlap writes. Must be reconciled with the `wx.CallAfter` thread-safety invariant.
- Safe modification: Guard shared caches with locks; never mutate wx GUI state off the main thread; route all UI updates through `wx.CallAfter` (55 call sites present in `src/`).
- Test coverage: settings and database have dedicated tests (`tests/test_settings.py`, others); concurrency paths are largely untested.

**Self-updating runtime components:**
- Files: `src/utils.py` (yt-dlp, Deno, InnerTube/youtubei, POT provider update functions ~lines 936-1360)
- Why fragile: Version resolution reads/writes lockfiles and runtime config (`_read_youtubei_lock_version`, `_write_youtubei_runtime_config`) and shells out to `deno cache`. A partial/failed update can leave inconsistent versions.
- Safe modification: Change one updater at a time; keep the corrupt-archive discard path (`_discard_bad_yt_dlp`) intact.

## Scaling Limits

**Not applicable** — single-user desktop application; no multi-tenant or high-throughput server component.

## Dependencies at Risk

**yt-dlp not a pinned dependency:**
- Risk: `yt-dlp` is absent from `pyproject.toml` dependencies; it is loaded dynamically from a downloaded archive at runtime (`load_yt_dlp`). Version and provenance are managed by the app itself rather than the lockfile.
- Impact: Reproducibility gap — the running yt-dlp version is not captured in `uv.lock`; a bad remote update can break extraction for all users.
- Migration plan: Consider pinning a baseline yt-dlp (or its wheel) in build deps and treating runtime updates as opt-in overlays with rollback.

**Extraction stack tightly coupled to YouTube internals:**
- Risk: `py-yt-search==0.8.0`, `prismatoid>=0.17.3`, Deno/InnerTube bridge, and POT provider all track YouTube's changing anti-bot surface.
- Impact: YouTube changes routinely break download/playback; multiple moving parts increase breakage surface.
- Migration plan: Maintain the update mechanisms and monitor upstream; keep the youtube-pot-security and innertube-rpc-bridge runbooks current.

## Missing Critical Features

**No automated signature verification of updates:**
- Problem: Update installer and downloaded runtimes are executed/imported without cryptographic verification (see Security).
- Blocks: A trustworthy auto-update story for a security-sensitive desktop app.

## Test Coverage Gaps

**Thread-safety / concurrency paths:**
- What's not tested: Interactions between background worker threads and wx GUI via `wx.CallAfter`; races around module-level caches (`_audio_devices_cache`, settings `_save_timer`).
- Files: `src/media_player/mpv_backend.py`, `src/settings_handler.py`, `src/async_utils.py`
- Risk: Silent GUI corruption or dropped screen-reader announcements that only manifest under real timing.
- Priority: High

**Runtime updater / dynamic yt-dlp loading:**
- What's not tested: Failure/rollback paths in `load_yt_dlp`, `download_yt_dlp`, `update_deno`, `install_youtubei_version`.
- Files: `src/utils.py:619-1360`
- Risk: A regression in update logic bricks extraction for shipped clients.
- Priority: High

**Skipped/xfail tests:**
- What's not tested: 6 `skip`/`xfail` markers present across `tests/`.
- Files: `tests/` (grep `@pytest.mark.skip`, `pytest.skip`, `xfail`)
- Risk: Skipped assertions may hide platform-specific (Linux/Wayland) regressions.
- Priority: Medium

---

*Concerns audit: 2026-09-28*
