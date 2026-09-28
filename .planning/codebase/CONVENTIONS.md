---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# Coding Conventions

**Analysis Date:** 2026-09-28

## Naming Patterns

**Files:**
- `snake_case.py` for all modules: `download_handler`, `settings_handler.py`, `pot_provider_service.py`, `youtube_url_utils.py`.
- Handler/service suffixes signal role: `*_handler.py` (feature coordinators), `*_service.py` (long-lived singletons), `*_client.py` (thin wrappers, e.g. `speech_client.py`).
- Test files mirror the subject with a `test_` prefix in `tests/`: `test_downloader.py`, `test_pot_provider_service.py`.

**Functions:**
- `snake_case` for all functions and methods: `get_audio_download_format`, `configure_py_yt_subprocess`, `_base_options`.
- Leading underscore for module/class internals: `_fallback_format_for_kbps`, `_progress_hook`, `_WindowlessSubprocess`.

**Variables:**
- `snake_case` locals; module-level singletons are lowercase instances (`deno_service`, `pot_service`, `logger`).
- Module-level constants are `UPPER_SNAKE_CASE`: `AUDIO_KBPS_FORMAT_MAP`.

**Types/Classes:**
- `PascalCase`: `Downloader`, `DownloadCancelled`, `WatchHistory`, `_WindowlessSubprocess`.
- Custom exceptions end in a descriptive noun (`DownloadCancelled`).

## Code Style

**Formatting:**
- `ruff format` (Ruff 0.16.8, pinned). Enforced by pre-commit (`ruff-format`) and a pre-push `ruff format --check .`.
- 4-space indentation, double quotes, trailing commas in multi-line calls (Ruff default profile).

**Linting:**
- `ruff check` targeting `py314`; source roots `src`, `tests`, `scripts` (`[tool.ruff]` in `pyproject.toml`).
- Globally ignored rules: `BLE001` (blind `except Exception`) and `S110` (`try/except/pass`). Blind excepts are an accepted pattern here.
- Type checking is disabled: `[tool.ty.rules] all = "ignore"`.
- Per-line suppressions use `# noqa: <CODE>` (e.g. `# noqa: F401` on re-exported symbols in `src/utils.py`, `# noqa: PLE2502` for raw RLM chars in translatable strings — see MEMORY note).

## Import Organization

**Order (Ruff isort default):**
1. Standard library (`import os`, `import logging`, `import threading`)
2. Third-party (`import requests`, `import wx`)
3. First-party / local (`import application`, `import paths`, `from language_handler import _`)

**Path Aliases:**
- No aliases. `src/` is placed on `sys.path` via `[tool.pytest.ini_options] pythonpath = ["src"]` (tests) and PyInstaller config (runtime), so modules import each other by bare name (`import paths`, `from database import WatchHistory`).

## Error Handling

**Patterns:**
- Broad `except Exception` is deliberately permitted (`BLE001`/`S110` ignored) so background/media callbacks never crash the GUI thread.
- Domain-specific exceptions for control flow: `DownloadCancelled` raised from `_progress_hook` when a cancel checker returns true.
- User-facing failures are announced to the screen reader immediately via `speech_client.speak(msg, interrupt=True)` and surfaced through wx dialogs — never silently swallowed at the UI layer.

## Logging

**Framework:** stdlib `logging`.

**Patterns:**
- Every module defines `logger = logging.getLogger(__name__)` at module top (`src/utils.py`, `src/database.py`, `src/deno_service.py`, `src/cookies_manager.py`).
- Root logger configured once at app entry (`src/accessible_youtube_downloader_pro.py`).
- Use `logger.debug/info/warning/error`; do not use `print` in `src/` (reserved for `scripts/`).

## Comments

**When to Comment:**
- Explain non-obvious platform workarounds (e.g. `CREATE_NO_WINDOW` subprocess wrapping for Windows in `src/utils.py`).
- Annotate suppressions with the reason where non-trivial.

**JSDoc/TSDoc:**
- Not applicable (Python). Module/function docstrings are used sparingly, mainly on scripts and public helpers.

## Function Design

**Size:** Small, single-purpose helpers (`clean_progress_text`, `_fallback_format_for_kbps`). Format-selection logic is factored into pure functions returning strings for testability.

**Parameters:** Constructors take explicit positional args plus keyword flags (`Downloader(url, dest, fmt, ..., convert=True, cancel_checker=...)`). Prefer keyword args for optional behavior.

**Return Values:** Pure helpers return plain data (strings/dicts); side-effecting methods return `None`. Cancellation is signaled by raising, not by return sentinels.

## Module Design

**Exports:** No `__all__`; modules expose bare names. Re-exports are marked with `# noqa: F401` (see `youtube_url_utils` re-export in `src/utils.py`).

**Singletons:** Shared services are instantiated once at module scope and imported by that instance (`from deno_service import deno_service`, `from pot_provider_service import pot_service`).

**Barrel Files:** Not used. Package subdirs (`download_handler/`, `media_player/`, `gui/`, `youtube_browser/`) expose submodules directly.

## Project Invariants (from CLAUDE.md / .cursorrules)

- **Thread safety:** never touch the wx GUI from a background/worker/MPV/yt-dlp thread; route through `wx.CallAfter(callable, *args)` or custom wx events.
- **Accessibility first:** every control needs an accessible label, `wx.TAB_TRAVERSAL`, and Enter/Space/Escape handling; announce state changes via `speech_client.speak`.
- **i18n discipline:** wrap all user-facing text in `_` (`from language_handler import _`); never concatenate — use named placeholders `_("Downloaded {title}").format(title=...)`; refresh `messages.pot` when strings change.
- **Path safety:** resolve paths through `paths.py` (`paths.settings_path()`, `paths.get_app_path()`); never hardcode `%APPDATA%`/absolute paths; honor portable mode.

---

*Convention analysis: 2026-09-28*
