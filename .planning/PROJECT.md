# HexPlayer — Code Health & Security Hardening

## What This Is

HexPlayer (Accessible YouTube Downloader Pro) is a mature Windows-first desktop YouTube client engineered for blind and visually impaired users — screen-reader-first, keyboard-driven, with wxPython GUI + CLI front-ends over a shared service layer (MPV playback, yt-dlp downloads, Deno/InnerTube search, SponsorBlock, PO-token anti-bot, cookie auth, EN/AR localization).

This milestone is a **code-health and security-hardening pass**: fix the high-impact problems catalogued in `.planning/codebase/CONCERNS.md` so that failures surface instead of being silently swallowed, credential handling and startup are tightened, and the riskiest paths gain test coverage — all without regressing the accessibility, thread-safety, i18n, and path-safety invariants in `CLAUDE.md`.

## Core Value

Blind and visually impaired users can navigate, play, and download YouTube content entirely by keyboard with immediate, reliable screen-reader feedback. Every change in this milestone must preserve that — and errors that were being swallowed must be announced or logged, never left silent.

## Requirements

### Validated

<!-- Existing, shipped capabilities inferred from the codebase map — the baseline this milestone must not regress. -->

- ✓ Screen-reader-first accessible GUI (wxPython) with keyboard navigation and TTS via Prism — existing
- ✓ MPV-based media playback (ctypes libmpv binding, transport controls, equalizer, timecodes) — existing
- ✓ yt-dlp download engine with progress events routed through `wx.CallAfter`/custom wx events — existing
- ✓ YouTube search / channels / playlists via py-yt and a Deno/InnerTube JSON-RPC bridge — existing
- ✓ SponsorBlock segment handling, PO-token anti-bot, and cookie authentication — existing
- ✓ CLI front-end (argparse) sharing the service/infra layer, plus a browser-extension native messaging host — existing
- ✓ SQLite (WAL) state store, INI settings, portable/frozen path resolution, EN/AR i18n — existing
- ✓ Windows (PyInstaller + Inno) and Linux (deb/rpm/tar.xz) packaging — existing

### Active

<!-- This milestone's scope. Building toward these. -->

- [ ] Fully re-enable Ruff `BLE001`/`S110`: audit the ~206 broad exception handlers (67 bare `except: pass`), narrow to expected types, log at warning/error where swallowed, and turn the lint rules back on with CI green
- [ ] Remove the URL-leaking DEBUG log line (`src/utils.py:1963`) and any INFO-level logging that leaks full URLs
- [ ] Harden cookie/credential handling: restrictive file permissions on cookie files; stop logging cookie paths alongside URLs
- [ ] Non-crypto hardening of runtime yt-dlp loading: fetch updates over HTTPS from a pinned source, remove the injected `sys.path` entry after load, keep archive-validity checks
- [ ] Make yt-dlp loading lazy (first-use, not at import) so GUI/CLI startup and test collection are no longer blocked
- [ ] Add thread-safety/concurrency test coverage: worker→GUI `wx.CallAfter` paths and races around module-level caches (`_audio_devices_cache`, settings `_save_timer`); guard shared caches with locks where tests reveal gaps
- [ ] Add runtime-updater test coverage: failure/rollback paths in `load_yt_dlp`, `download_yt_dlp`, `update_deno`, `install_youtubei_version`
- [ ] Audit the 6 `skip`/`xfail` markers in `tests/` — re-enable or document why each stays skipped (Medium priority)

### Out of Scope

<!-- Explicitly deferred, with reasoning to prevent re-adding. -->

- Update signature/authenticity verification (installer, downloaded runtimes, yt-dlp archive) — net-new feature requiring signing infrastructure in CI and key management; belongs in its own dedicated milestone
- yt-dlp dependency pinning + rollback overlay — coupled to the update-mechanism rework; moves with the signing/update-hardening milestone
- `src/utils.py` god-module split into focused modules — large refactor; deferred to keep this milestone focused on high-impact hardening
- Embedded-video-on-Wayland regression — not in the high-impact cut; requires a Linux/Wayland session to reproduce and verify, which the Windows-primary dev environment can't do
- Decoupling the extraction stack from YouTube internals — inherent to the domain; handled by ongoing maintenance of the existing update mechanisms, not a discrete fix

## Context

- **Codebase map:** full analysis in `.planning/codebase/` (ARCHITECTURE, STACK, STRUCTURE, CONCERNS, CONVENTIONS, INTEGRATIONS, TESTING), mapped at commit `aa0548e` on 2026-09-28.
- **Stack:** Python ≥3.14 (pinned 3.14.7), wxPython 4.3.1, `uv` package manager, bundled Deno + MPV + FFmpeg, `pytest` 9 + `pytest-asyncio`, Ruff 0.16.8 (`target-version = py314`), Babel for i18n, PyInstaller for packaging.
- **yt-dlp is not a pinned dependency** — it is downloaded and imported at runtime from a self-updating archive (`load_yt_dlp`), which is the root of several security and startup concerns.
- **Tension to respect:** the current `BLE001`/`S110` suppression directly undermines the `CLAUDE.md` invariant "announce errors immediately" — silent swallows can drop screen-reader announcements and hide thread crashes. Narrowing handlers is the fix, not deletion.
- **Invariants (`CLAUDE.md`):** `wx.CallAfter` for all cross-thread GUI updates; screen-reader accessibility first; i18n discipline (`_()`, no hardcoded strings, re-extract `messages.pot`); path safety via `paths.py`; mandatory preflight (`uv run python scripts/agent_preflight.py`) before completing any task.

## Constraints

- **Tech stack**: Python 3.14 / wxPython 4.3.1 / `uv` — stay on the pinned toolchain; no framework swaps.
- **Accessibility**: All changes preserve screen-reader announcements and keyboard navigation; replace swallowed errors with logging/announcement, never silent removal.
- **Thread safety**: GUI touched only on the main thread; exception-handler narrowing must not break `wx.CallAfter` routing.
- **i18n**: No hardcoded user-facing strings; re-extract `messages.pot` if any user-facing text changes.
- **Path safety**: Paths resolved via `paths.py`; portable and frozen (`sys._MEIPASS`) modes respected.
- **Verification**: `uv run python scripts/agent_preflight.py` and the `pytest` suite must pass before any task is considered done.
- **Environment**: Windows-primary dev/verify environment; Linux/Wayland-specific fixes cannot be verified here (why the Wayland bug is out of scope).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| High-impact cut of CONCERNS.md for this milestone | Focus on security + URL leak + lazy load + High-priority test gaps; defer big refactors | — Pending |
| Fully re-enable `BLE001`/`S110` (not incremental) | User chose the full audit; restores the "announce/log errors" a11y invariant and blocks regressions | — Pending |
| Defer update signature verification to its own milestone | Net-new capability (signing infra, key management); out of place in a hardening-existing-code pass | — Pending |
| Exclude the embedded-video-on-Wayland bug | Needs a Linux/Wayland session to reproduce and verify; not high-impact for Windows-primary users | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-28 after initialization*
