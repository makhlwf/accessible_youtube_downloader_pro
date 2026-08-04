# Contributing to HexPlayer (Accessible YouTube Downloader Pro)

First off, thank you for considering contributing to **HexPlayer**! Community contributions help make YouTube accessible, efficient, and enjoyable for blind and visually impaired users worldwide.

---

## Table of Contents

1. [Code of Conduct & Core Values](#code-of-conduct--core-values)
2. [How Can I Contribute?](#how-can-i-contribute)
3. [Developer Documentation & Environment Setup](#developer-documentation--environment-setup)
4. [Coding & Accessibility Guidelines](#coding--accessibility-guidelines)
5. [Quality Assurance & Pre-Commit Checklist](#quality-assurance--pre-commit-checklist)
6. [Submitting a Pull Request](#submitting-a-pull-request)
7. [License](#license)

---

## Code of Conduct & Core Values

HexPlayer is engineered specifically around **accessibility**, **reliability**, and **screen-reader performance**. When contributing, please keep the following core values in mind:

1. **Accessibility First:** Every feature, dialog, control, and shortcut must be 100% accessible via keyboard navigation and all Windows screen readers (NVDA, JAWS, Narrator, System Access, etc. via Prism).
2. **Respect & Inclusion:** We foster an open, welcoming, and inclusive community for all contributors and users regardless of experience level.
3. **No Breaking Accessibility Regressions:** Custom, mouse-only, or owner-drawn controls that break screen reader focus or keyboard control are strictly disallowed.

---

## How Can I Contribute?

### 1. Reporting Bugs
Before creating a bug report, please search existing [GitHub Issues](https://github.com/makhlwf/accessible_youtube_downloader_pro/issues) to verify if the issue has already been reported.

When filing a bug report, please include:
- **Application version:** (e.g. `3.6.0` or git commit hash)
- **Environment details:** Windows version and active screen reader or speech engine (e.g. Windows 11 64-bit, NVDA / JAWS / Narrator / System Access / OneCore / SAPI)
- **Steps to reproduce:** Clear, step-by-step instructions to reproduce the issue
- **Expected vs. Actual behavior:** Clear description of what should happen vs. what actually occurred
- **Error output or traceback:** Any relevant log output or stack traces

### 2. Suggesting Enhancements
Feature requests are always welcome! When proposing a feature, please explain:
- **Use case:** Why the feature is beneficial for accessible YouTube browsing or downloading
- **Interaction model:** How keyboard focus, mnemonics, and screen reader speech announcements should behave

### 3. Submitting Pull Requests
We welcome code contributions, documentation improvements, translation updates, and bug fixes!

---

## Developer Documentation & Environment Setup

For a deep technical breakdown of the architecture, SQLite schemas, Deno/YouTube.js RPC protocol, MPV player Ctypes wrapper, native messaging host, and packaging machinery, see the **[DEVELOPMENT.md](DEVELOPMENT.md)** guide.

### Development Quickstart

1. **Fork & Clone the repository:**
   ```powershell
   git clone https://github.com/YOUR-USERNAME/accessible_youtube_downloader_pro.git
   cd accessible_youtube_downloader_pro
   ```

2. **Install `uv` dependency manager (if not already installed):**
   ```powershell
   winget install astral-sh.uv
   ```

3. **Sync locked dependencies:**
   ```powershell
   uv sync
   ```

4. **Launch the application from source:**
   ```powershell
   uv run python src\accessible_youtube_downloader_pro.py
   ```

---

## Coding & Accessibility Guidelines

When writing code for HexPlayer, adhere strictly to these principles:

### ♿ Accessibility Standards (Mandatory)
- **Native wxPython Widgets:** Use standard `wx.ListBox`, `wx.Button`, `wx.TextCtrl`, `wx.Menu`, etc. Avoid custom mouse-centric widgets.
- **Keyboard Navigation & Mnemonics:** Ensure proper tab traversal order in modal dialogs (`wx.TAB_TRAVERSAL`) and provide keyboard mnemonics (e.g., `&Search` for `Alt+S`).
- **Screen Reader Announcements (`speak()`):** Call `speak(message)` from `src/utils.py` whenever asynchronous events complete or state changes take place.
- **Standardized Hotkeys:** Maintain consistency with established keyboard shortcuts (`Ctrl+F` for Search, `Ctrl+D` for Download, `Space` for Play/Pause, Arrow keys for volume/seeking).

### 🧵 Thread Safety & UI Updates
- **`wx.CallAfter` Dispatch:** Background threads (MPV callbacks, Deno RPC calls, `yt-dlp` download threads) **must never** directly modify wxPython UI elements. Always dispatch UI updates via `wx.CallAfter()`.

### 📂 Dynamic Paths
- Use `paths.py` helper functions (`settings_path()`, `get_app_path()`) rather than hardcoding file paths.

### 🌐 Internationalization (i18n)
- Wrap all user-visible strings with `_("Translatable string")` imported from `language_handler`.
- When adding or modifying translatable strings, update `messages.pot` and verify translations:
  ```powershell
  uv run pybabel extract -F babel.cfg -k _ -o messages.pot .
  uv run python scripts/check_translations.py
  ```

---

## Quality Assurance & Pre-Commit Checklist

Before submitting a Pull Request, verify that your changes pass all automated checks:

1. **Linting:**
   ```powershell
   uv run ruff check .
   ```

2. **Automated Test Suite:**
   ```powershell
   uv run pytest tests/
   ```

3. **Translation Catalog Check:**
   ```powershell
   uv run python scripts/check_translations.py
   ```

4. **Manual Accessibility Verification:**
   - Verify full keyboard navigation using `Tab`, `Shift+Tab`, and `Alt` mnemonics.
   - Confirm screen reader announcements function properly with any active Windows screen reader (NVDA, JAWS, Narrator, etc.) or TTS engine via Prism.

---

## Submitting a Pull Request

1. Create a feature branch:
   ```powershell
   git checkout -b feature/accessible-feature-name
   ```

2. Commit changes with clear, descriptive messages:
   ```powershell
   git commit -m "feat(gui): add accessible shortcut for format selection dialog"
   ```

3. Push your branch to GitHub:
   ```powershell
   git push origin feature/accessible-feature-name
   ```

4. Open a Pull Request on GitHub against the `master` branch.
   - Provide a clear summary of your changes.
   - Link any related GitHub issues (e.g. `Fixes #42`).

---

## License

By contributing to HexPlayer, you agree that your contributions will be licensed under the project's [GNU General Public License v3.0](LICENSE).
