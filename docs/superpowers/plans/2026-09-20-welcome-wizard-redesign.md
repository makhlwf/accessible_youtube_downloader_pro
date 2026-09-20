# Accessible Welcome & Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-implement the accessible first-run welcome and setup wizard (`WelcomeDialog`) with configuration first, friendly component readiness, an interactive keyboard cheat sheet, and clean launch options.

**Architecture:** A 4-panel modal `wx.Dialog` managed with linear step transitions, strict focus management, screen reader announcements via `speech_client`, and atomic settings persistence through `settings_handler`.

**Tech Stack:** Python 3.11+, wxPython 4.2+, pybabel (gettext i18n), pytest.

## Global Constraints
- `wx.CallAfter` for all GUI updates from background threads.
- All user-facing strings must use `_()` from `language_handler`.
- No string concatenation for localized text; use named format strings.
- Screen reader accessibility first: explicit labels, keyboard traversal (`wx.TAB_TRAVERSAL`), and immediate announcements via `speech_client.speak(msg, interrupt=True)`.
- Use `_set_bold_title` and `_safe_wrap` helpers to ensure safe headless testing with mocked wx objects.
- Preflight verification (`uv run python scripts/agent_preflight.py`) must pass 100%.

---

### Task 1: Refactor `WelcomeDialog` Step Panels & Navigation

**Files:**
- Modify: `src/gui/welcome_dialog.py`
- Test: `tests/test_welcome_dialog.py`

**Interfaces:**
- Consumes: `settings_handler.get_instance()`, `speech_client.speech_client`, `language_handler._`, `utils.download_yt_dlp`
- Produces: `WelcomeDialog(parent=None)` with methods `_create_step1_panel()`, `_create_step2_panel()`, `_create_step3_panel()`, `_create_step4_panel()`, `_show_step(step_index)`, `_on_finish(event)`, `_save_settings()`

- [ ] **Step 1: Update unit tests in `tests/test_welcome_dialog.py` to match the 4-step specification**

```python
# tests/test_welcome_dialog.py
import pytest
from unittest.mock import MagicMock, patch
import wx

def test_welcome_dialog_step_navigation():
    from gui.welcome_dialog import WelcomeDialog
    with patch("gui.welcome_dialog.speech_client") as mock_speech:
        dlg = WelcomeDialog(parent=None)
        assert dlg.current_step == 0
        assert dlg.btn_back.IsEnabled() is False
        assert dlg.btn_next.GetLabel() == "Next >"

        # Advance to Step 2
        dlg._on_next(None)
        assert dlg.current_step == 1
        assert dlg.btn_back.IsEnabled() is True
        assert mock_speech.speak.called

        # Advance to Step 3
        dlg._on_next(None)
        assert dlg.current_step == 2

        # Advance to Step 4
        dlg._on_next(None)
        assert dlg.current_step == 3
        assert dlg.btn_next.GetLabel() == "Finish"

        # Go Back to Step 3
        dlg._on_back(None)
        assert dlg.current_step == 2
        assert dlg.btn_next.GetLabel() == "Next >"
```

- [ ] **Step 2: Run test to verify failure with current code**

Run: `uv run pytest tests/test_welcome_dialog.py::test_welcome_dialog_step_navigation -v`
Expected: FAIL due to step labels or control mismatch.

- [ ] **Step 3: Implement the new 4-step `WelcomeDialog` in `src/gui/welcome_dialog.py`**

Refactor `WelcomeDialog` with:
- Step 1 (`_create_step1_panel`): Language choice (`wx.Choice`), Playback mode radio box (`wx.RadioBox` with Audio vs Video), Clipboard auto-detect (`wx.CheckBox`).
- Step 2 (`_create_step2_panel`): Downloader readiness (`yt-dlp` path check), friendly status label, and "Download or Update" button with background worker.
- Step 3 (`_create_step3_panel`): Categorized keyboard shortcuts cheat sheet (`wx.ListCtrl` with 2 columns: Shortcut and Action) plus button to launch full shortcuts dialog.
- Step 4 (`_create_step4_panel`): Show on startup checkbox, "Open User Documentation (F1)" button, and "Finish and Launch HexPlayer" button.
- `_show_step(step_idx)`: Switches visible panel, updates button labels, manages focus, and announces step transition.
- `_save_settings()`: Saves language, playback mode, clipboard detection, and `welcome_completed`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_welcome_dialog.py::test_welcome_dialog_step_navigation -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add src/gui/welcome_dialog.py tests/test_welcome_dialog.py
git commit -m "feat(gui): refactor welcome dialog to 4-step configuration first wizard"
```

---

### Task 2: Comprehensive Unit Tests for Welcome Wizard

**Files:**
- Modify: `tests/test_welcome_dialog.py`

**Interfaces:**
- Consumes: `WelcomeDialog`, `settings_handler`, `speech_client`
- Produces: Complete test coverage for step transitions, setting persistence, cheat sheet content, downloader trigger, and startup hooks.

- [ ] **Step 1: Add detailed test cases for all 4 steps and settings persistence**

```python
# tests/test_welcome_dialog.py
def test_step1_settings_persistence():
    from gui.welcome_dialog import WelcomeDialog
    with patch("gui.welcome_dialog.settings_handler") as mock_settings, \
         patch("gui.welcome_dialog.speech_client"):
        settings_instance = MagicMock()
        mock_settings.get_instance.return_value = settings_instance
        settings_instance.get_setting.side_effect = lambda k, default=None: {
            "language": "en",
            "preferred_media_mode": "audio",
            "auto_detect_clipboard": True,
        }.get(k, default)

        dlg = WelcomeDialog(parent=None)
        dlg.EndModal = MagicMock()
        dlg.choice_lang.SetSelection(0)
        dlg.radio_mode.SetSelection(1) # Video
        dlg.chk_clipboard.SetValue(False)

        dlg._on_finish(None)
        settings_instance.set_setting.assert_any_call("preferred_media_mode", "video")
        settings_instance.set_setting.assert_any_call("auto_detect_clipboard", False)
        settings_instance.set_setting.assert_any_call("welcome_completed", True)

def test_step2_component_readiness_and_download():
    from gui.welcome_dialog import WelcomeDialog
    with patch("gui.welcome_dialog.utils.download_yt_dlp") as mock_dl, \
         patch("gui.welcome_dialog.speech_client"):
        dlg = WelcomeDialog(parent=None)
        dlg._show_step(1)
        dlg.btn_download_ytdlp.Command(wx.CommandEvent(wx.wxEVT_BUTTON, dlg.btn_download_ytdlp.GetId()))
        mock_dl.assert_called_once_with(parent=dlg)

def test_step3_shortcuts_cheat_sheet_populated():
    from gui.welcome_dialog import WelcomeDialog
    with patch("gui.welcome_dialog.speech_client"):
        dlg = WelcomeDialog(parent=None)
        dlg._show_step(2)
        assert dlg.list_shortcuts.GetItemCount() > 5

def test_step4_startup_toggle_controls_welcome_completed():
    from gui.welcome_dialog import WelcomeDialog
    with patch("gui.welcome_dialog.settings_handler") as mock_settings, \
         patch("gui.welcome_dialog.speech_client"):
        settings_instance = MagicMock()
        mock_settings.get_instance.return_value = settings_instance
        dlg = WelcomeDialog(parent=None)
        dlg.EndModal = MagicMock()
        dlg._show_step(3)

        # If user unchecks "Show on startup", welcome_completed is True
        dlg.chk_show_on_startup.SetValue(False)
        dlg._on_finish(None)
        settings_instance.set_setting.assert_any_call("welcome_completed", True)
```

- [ ] **Step 2: Run test suite**

Run: `uv run pytest tests/test_welcome_dialog.py -v`
Expected: PASS (all tests pass).

- [ ] **Step 3: Commit test suite**

```bash
git add tests/test_welcome_dialog.py
git commit -m "test: add comprehensive tests for 4-step welcome dialog"
```

---

### Task 3: Translation Extraction, Localization, and Compilation

**Files:**
- Modify: `messages.pot`
- Modify: `src/languages/ar/LC_MESSAGES/HexPlayer.po`
- Modify: `src/languages/ar/LC_MESSAGES/HexPlayer.mo`
- Modify: `src/languages/en/LC_MESSAGES/HexPlayer.po`
- Modify: `src/languages/en/LC_MESSAGES/HexPlayer.mo`

**Interfaces:**
- Consumes: babel.cfg, pybabel CLI
- Produces: Up-to-date translation catalogs with 0 missing strings.

- [ ] **Step 1: Extract translatable strings into `messages.pot`**

Run: `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`
Expected: `messages.pot` generated with all new wizard strings.

- [ ] **Step 2: Update Arabic and English `.po` files**

Run: `uv run pybabel update -i messages.pot -d src/languages -D HexPlayer`
Translate all new untranslated messages in `src/languages/ar/LC_MESSAGES/HexPlayer.po`.

- [ ] **Step 3: Compile `.mo` catalogs**

Run: `uv run pybabel compile -D HexPlayer -d src/languages`
Expected: Compiled `.mo` binary catalogs generated for `ar` and `en`.

- [ ] **Step 4: Check translation integrity**

Run: `uv run python scripts/check_translations.py`
Expected: Translation checks PASS with 0 untranslated strings.

- [ ] **Step 5: Commit translation catalogs**

```bash
git add messages.pot src/languages/
git commit -m "i18n: extract and compile translations for revised welcome wizard"
```

---

### Task 4: Mandatory Preflight Verification

**Files:**
- Verification: Entire repository

- [ ] **Step 1: Run preflight suite**

Run: `uv run python scripts/agent_preflight.py`
Expected:
1. `scripts/verify_skills.py` PASS
2. `uv run ruff check .` PASS
3. `uv run python scripts/check_translations.py` PASS
4. `uv run pytest tests/` PASS

- [ ] **Step 2: Verify git status is clean**

Run: `git status`
Expected: Working tree clean, everything committed.
