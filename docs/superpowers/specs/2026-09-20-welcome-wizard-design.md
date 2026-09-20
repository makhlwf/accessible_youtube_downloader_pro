# HexPlayer Welcome & Setup Guide Design Specification

**Date**: 2026-09-20  
**Status**: Approved  
**Topic**: Accessible First-Run Onboarding & Configuration Wizard (HexPlayer)

---

## 1. Overview & Context
HexPlayer (Accessible YouTube Downloader Pro) is a specialized Windows desktop YouTube client engineered specifically for blind and visually impaired users.

First-time users need an accessible, respectful, and streamlined onboarding experience that puts essential configurations upfront (language, playback mode, clipboard detection), avoids technical or scripted gimmicks (e.g. testing low-level MPV or audio backend drivers), verifies external tool readiness (yt-dlp), provides a structured keyboard shortcut cheat sheet, and allows seamless transition into the main application.

---

## 2. Goals & Non-Goals

### Goals
1. **Configuration First**: Allow users to configure interface language, audio/video mode, and clipboard auto-detection on the very first screen.
2. **Component Readiness**: Provide a clean, non-technical status check for `yt-dlp` with an optional 1-click install/update mechanism.
3. **Keyboard & Workflow Cheat Sheet**: Present an interactive, arrowable cheat sheet of essential shortcuts and core workflows.
4. **Accessible Navigation**: Strictly manage focus on step transitions, announce steps via `speech_client.speak(..., interrupt=True)`, and support full keyboard traversal.
5. **Thread Safety & i18n**: Follow all repository invariants (`wx.CallAfter`, `_()` wrapper for all strings, no string concatenation).
6. **Persistence**: Save choices to `settings_handler` upon completion or exit.

### Non-Goals
- No low-level technical hardware or library testing buttons (e.g., MPV device enumeration tests).
- No disconnected, scripted action buttons that simulate actions without real context.
- No forced multi-step account login or authentication requirements during the welcome tour.

---

## 3. Step-by-Step Flow & Information Architecture

The wizard is implemented as a 4-step modal dialog (`wx.Dialog`) titled `_("HexPlayer Welcome & Setup Guide")`:

### Step 1: Initial Configuration (First Thing First)
- **Heading**: `_("Step 1 of 4: Initial Configuration")`
- **Description**: Configure core preferences for your listening experience.
- **Controls**:
  - **Language Selection** (`wx.Choice`): Lists supported languages (English, Arabic, etc.). Updates active language setting immediately or upon finish.
  - **Playback Mode** (`wx.RadioBox`):
    - `_("Audio Mode (Fast, screen reader optimized, background listening)")`
    - `_("Video Mode (Displays video player window)")`
  - **Clipboard Auto-Detection** (`wx.CheckBox`):
    - `_("Automatically detect YouTube links copied to clipboard")`

### Step 2: Component Readiness
- **Heading**: `_("Step 2 of 4: Component Readiness")`
- **Description**: Verifies that external download tools are configured and ready. Clarifies that internal playback codecs (libmpv) are already bundled and operational.
- **Controls**:
  - **Downloader Engine Status** (`wx.StaticText`): Reports `_("Download Engine (yt-dlp): Ready")` or `_("Download Engine (yt-dlp): Update recommended / Not found")`.
  - **Download / Update Button** (`wx.Button`): `_("Download or Update Download Engine")` triggers background download with progress notifications and thread-safe UI updates.

### Step 3: Keyboard Shortcuts & Workflow Cheat Sheet
- **Heading**: `_("Step 3 of 4: Keyboard Shortcuts & Quick Workflows")`
- **Description**: An accessible, arrowable reference of primary keyboard shortcuts.
- **Controls**:
  - **Shortcuts List** (`wx.ListCtrl` with report style, accessible labels):
    - `Alt+S` or `Ctrl+F` — Focus Search Box
    - `Tab` / `Shift+Tab` — Move between Search, Results list, and Controls
    - `Enter` — Play selected video or playlist
    - `Space` — Play / Pause media
    - `Left / Right Arrows` — Seek 5 seconds backward / forward
    - `Up / Down Arrows` — Volume increase / decrease
    - `[` and `]` — Decrease / Increase playback speed
    - `M` — Mute / Unmute audio
    - `D` or `Alt+D` — Download selected media
    - `Ctrl+H` — Open History
    - `Ctrl+B` — Open Bookmarks / Favorites
  - **Full Shortcuts Button** (`wx.Button`): `_("Open Full Shortcuts Guide")` to view the comprehensive shortcut modal.

### Step 4: Ready to Go
- **Heading**: `_("Step 4 of 4: You are Ready to Go!")`
- **Description**: Setup is complete.
- **Controls**:
  - **Show on Startup Checkbox** (`wx.CheckBox`): `_("Show this welcome screen on startup")` (defaults to unchecked when completed).
  - **Documentation Button** (`wx.Button`): `_("Open User Documentation (F1)")` launches the user guide.
  - **Finish Button** (`wx.Button` - default focus): `_("Finish and Launch HexPlayer")` commits settings and dismisses dialog.

---

## 4. Navigation & Focus Management
- Bottom action bar on all screens: `[Back]`, `[Next] / [Finish]`, `[Skip / Close]`.
- On step change:
  1. Hide previous panel, show next panel.
  2. Set focus to the step's heading or first interactive element.
  3. Call `speech_client.speak(_("Step {current} of {total}: {title}").format(...), interrupt=True)`.
  4. Enable/disable `[Back]` (disabled on Step 1).

---

## 5. Settings Persistence & Data Flow
- `settings_handler.get_instance()` manages:
  - `welcome_completed`: bool (set to True upon completing or skipping).
  - `language`: string (e.g. "en", "ar").
  - `preferred_media_mode`: string ("audio" or "video").
  - `auto_detect_clipboard`: bool.
- Changes are committed cleanly on exit (`Finish` or `Skip`).

---

## 6. Testing & Quality Gates
- **Unit Tests** in `tests/test_welcome_dialog.py`:
  - Step navigation (Next / Back).
  - Screen reader speech calls.
  - Settings commitment for each configuration item.
  - Component readiness display and download invocation.
  - Cheat sheet list population.
  - First-run integration check on `HomeScreen`.
- **Preflight Verification**:
  - `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`
  - Update and compile `.po` / `.mo` catalogs for `ar` and `en`.
  - Run `uv run python scripts/agent_preflight.py` (skills check, ruff linter, translation check, pytest suite).
