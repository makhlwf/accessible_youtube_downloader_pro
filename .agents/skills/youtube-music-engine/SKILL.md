---
name: youtube-music-engine
description: Use when working on the YouTube Music experience — the in-place flip panel, ytmusicapi service wrapper, cookie-based auth bridge, music playback/radio, the YouTube Music settings tab, or any src/youtube_music/ module.
---

## Overview

The YouTube Music subsystem lives in `src/youtube_music/` and gives blind users an
accessible, screen-reader-first music experience built on
[`ytmusicapi`](https://github.com/sigma67/ytmusicapi) (pinned `ytmusicapi==1.12.3`).
It is a self-contained package that reuses HexPlayer's existing machinery rather than
duplicating it: stream resolution (`utils.get_playable_stream`), the player
(`media_player.media_gui.MediaGui`), downloads (`download_handler.downloader.start_media_download`),
background prefetch (`youtube_browser.scraper.Scraper`), theming, speech, config, and i18n.

ytmusicapi is a third metadata backend alongside `py_yt` and the Deno `service.js` bridge.
It speaks HTTP in-process, so music browse traffic never contends on the single Deno pipe;
only stream resolution flows through the shared yt-dlp path.

## When to Use

Use this skill when adding, debugging, or reviewing anything under `src/youtube_music/`,
the YouTube Music button/flip on `HomeScreen`, the YouTube Music settings tab in
`gui/settings_dialog.py`, the cookie→ytmusicapi auth bridge, or music playback and radio.

## Core Patterns & Invariants

- **The flip is in-place, never a new window.** `HomeScreen` holds a root sizer with the
  normal `self.panel` and a lazily-built sibling `YouTubeMusicPanel`. `open_music()` hides one
  and shows the other with `Show`/`Hide` + `Layout()` (wrapped in `Freeze`/`Thaw`), announces
  the mode via `speak`, and focuses the new list. `close_music()` reverses it.
- **ytmusicapi runs off the GUI thread.** It is synchronous and not thread-safe. Every call
  goes through `YTMusicService` (per-client lock) on a daemon thread; results return via
  `wx.CallAfter`. Never call it on the wx main thread.
- **Anonymous vs authenticated.** `YTMusicService._client(mode)` picks `anon`, `auth`, or
  `prefer_auth`. Search/browse work anonymously; home/library/likes/history and all writes need
  auth and raise `AuthRequiredError` when signed out so the UI can prompt a cookie import.
- **Auth reuses existing browser cookies.** `auth_bridge.build_browser_headers()` parses the same
  Netscape cookie file `cookies_manager` writes, mirroring `service.js` `parseCookies` (including
  synthesising `SAPISID` from `__Secure-3PAPISID`). ytmusicapi computes the SAPISIDHASH
  `Authorization` header itself. Never log cookie values.
- **Destructive writes are confirmed and announced.** `dialogs.confirm_destructive` (defaults to
  No, speaks on open) gates delete/rename playlist, unsubscribe, remove-from-history, and
  remove-from-playlist. Non-destructive writes announce success only.
- **Rows follow one schema.** `adapters.normalize_item` flattens any ytmusicapi item into the row
  dict; `adapters.YTMusicResult` implements the same duck-typed protocol as
  `youtube_browser.search_handler.SimpleResult`, preserving both `videoId` and `setVideoId`.
- **Speech uses `from speech_client import speak`** — there is no `speech_client` singleton.

## Quick Reference

| Need | Use |
| --- | --- |
| Shared service | `youtube_music.service.get_service()` / `reload_auth()` |
| Build auth headers | `youtube_music.auth_bridge.build_browser_headers(path)` |
| Normalise a payload | `youtube_music.adapters.normalize_items(items)` |
| Play a row | `youtube_music.playback.play_result(frame, result, index, audio_mode=True)` |
| Start a radio | `youtube_music.playback.start_radio(frame, result, index)` |
| Confirm a destructive write | `youtube_music.dialogs.confirm_destructive(parent, text)` |
| Run a write off-thread | `youtube_music.actions.run_write(frame, panel, fn, success_msg=..., destructive=...)` |
| Config keys | `youtube_music_enabled`, `youtube_music_default_audio_quality`, `youtube_music_filter_explicit`, `youtube_music_lyrics` |

## Implementation Procedures

- **A new browse surface:** add a factory in `views.py` returning a `CollectionView` whose
  `fetch` closure calls a `YTMusicService` wrapper and returns `adapters.normalize_items(...)`.
  Reach it from a `YouTubeMusicPanel.open_*` method via `show_view`.
- **A new write:** add a thin wrapper in `service.py` (mode `auth`), then a `YouTubeMusicPanel`
  method using `actions.run_write`; set `destructive=True` + `confirm_text` for anything that
  removes or deletes account data.
- **A new ytmusicapi method:** wrap it in `YTMusicService` with the correct `mode`; verify its
  real signature against the installed package (`uv run python -I -c "import inspect, ytmusicapi; print(inspect.signature(ytmusicapi.YTMusic.<method>))"`).
- **User-facing text:** author Arabic msgids via `from language_handler import _`, extract with
  `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`, update + compile the `ar`/`en`
  catalogs, and provide English in `src/languages/en/LC_MESSAGES/HexPlayer.po`.

## Common Mistakes & Anti-Patterns

- Calling ytmusicapi on the GUI thread, or sharing one client across threads without the lock.
- Assuming `get_home`/library/likes work anonymously — they need auth; handle `AuthRequiredError`.
- Passing only `videoId` to `remove_playlist_items` — it needs the track's `setVideoId`.
- Calling `get_lyrics` with a video id — it needs the lyrics `browseId` from `get_watch_playlist`.
- Logging cookie values or writing an `Authorization` header yourself.
- Hardcoding English or Arabic strings instead of `_()`.
- Opening a new window for YouTube Music instead of flipping the sibling panel in place.

## Verification & Quality Gates

- `uv run python scripts/agent_preflight.py` must pass (skills, ruff, translation freshness, pytest).
- Unit tests live in `tests/test_youtube_music_*.py`; cover empty/malformed payloads, missing auth,
  destructive confirm/cancel, and flip-while-playing. ytmusicapi is mocked in `tests/conftest.py`.
- Manual smoke with NVDA Speech Viewer: Ctrl+M flips and announces, anonymous search plays a track,
  importing cookies in Settings populates the home feed, a radio auto-advances, and a destructive
  action prompts for confirmation.
