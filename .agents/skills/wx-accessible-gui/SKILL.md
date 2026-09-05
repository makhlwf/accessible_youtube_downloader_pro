---
name: wx-accessible-gui
description: >-
  Use when developing, modifying, or debugging wxPython user interface components,
  dialogs, custom controls, keyboard navigation, or screen reader speech announcements.
---

# wxPython Accessible GUI Development

## Overview

HexPlayer is engineered specifically for blind and visually impaired users. Every graphical component must be completely navigable by keyboard and provide immediate, unambiguous auditory feedback via screen readers (NVDA, JAWS, OneCore, SAPI).

## When to Use

- Creating or modifying wxPython dialogs, panels, frames, or custom widgets in `src/gui/`.
- Fixing keyboard navigation issues (focus traps, missing tab stops, unhandled Enter/Escape keys).
- Implementing auditory status feedback and live announcements.
- Adjusting color themes, dark mode (`MSWEnableDarkMode`), or Windows high-contrast compatibility.
- Diagnosing GUI deadlocks or random crashes caused by background thread UI updates.

**When NOT to use:**
- Writing pure background data processing, network requests, or database queries with no UI interaction.

## Core Patterns & Invariants

### 1. Mandatory `wx.CallAfter` on Cross-Thread Calls
The wxPython main event loop runs on a single UI thread. Modifying any widget from background threads, worker threads, or async coroutines causes native Windows crashes, memory corruption, or deadlocks.

```python
# ❌ INCORRECT: Direct call from background worker thread
def on_search_completed(self, results):
    self.results_list.Set(results)  # CRASH OR DEADLOCK RISK


# ✅ CORRECT: Marshaled to main GUI thread
def on_search_completed(self, results):
    wx.CallAfter(self._update_results_ui, results)


def _update_results_ui(self, results):
    self.results_list.Set(results)
    self.results_list.SetFocus()
```

### 2. Tab Traversal on Containers
Custom panels and composite controls must enable keyboard navigation:

```python
# ✅ REQUIRED: Include wx.TAB_TRAVERSAL on composite container panels
class CustomCardPanel(wx.Panel):
    def __init__(self, parent, id=wx.ID_ANY):
        super().__init__(parent, id, style=wx.TAB_TRAVERSAL)
```

### 3. Screen Reader Speech Integration
Always announce state transitions, completion messages, and errors using `speech_client`:

```python
from language_handler import _
from speech_client import speech_client

# Announce immediate feedback
speech_client.speak(_("Playback started."), interrupt=True)
```

### 4. Dialog Focus Restoration
Blind users rely heavily on focus position. When a modal dialog closes, focus must return to the triggering control:

```python
def open_options(self, event):
    calling_control = wx.Window.FindFocus()
    dlg = SettingsDialog(self)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
        if calling_control and calling_control.IsShown():
            calling_control.SetFocus()
```

## Quick Reference

| Operation | Implementation |
| :--- | :--- |
| **Cross-Thread UI Dispatch** | `wx.CallAfter(self.method, *args)` |
| **Speak to Screen Reader** | `speech_client.speak(_("Message"), interrupt=True)` |
| **Get Focused Window** | `focused = wx.Window.FindFocus()` |
| **Restore Focus** | `if ctrl and ctrl.IsShown(): ctrl.SetFocus()` |
| **Handle Modal Dialog** | `dlg = MyDialog(self); dlg.ShowModal(); dlg.Destroy()` |
| **Dark Mode Application** | `theme_handler.apply_theme(self)` |

## Implementation Procedures

### Step 1: Creating an Accessible Modal Dialog
1. Subclass `wx.Dialog`.
2. Apply `wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER`.
3. In `__init__`, bind key hooks for standard keys:
   ```python
   self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
   ```
4. In `_on_char_hook`, close on Escape (`wx.ID_CANCEL`) and confirm on Enter (`wx.ID_OK`).
5. Ensure every control has an explicit label or accessible name (`control.SetName(_("Label"))`).

### Step 2: Adding Interactive Accessible Lists
1. Use `wx.ListBox` or virtual `wx.ListCtrl`.
2. Bind `wx.EVT_LISTBOX` for selection change speech updates.
3. Bind `wx.EVT_LISTBOX_DCLICK` and `wx.EVT_KEY_DOWN` (listening for `WXK_RETURN`) to execute default action.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Mouse-only hover effects | Screen reader users cannot use hover | Trigger info on keyboard focus (`wx.EVT_SET_FOCUS`) |
| Silent state changes | User does not know background task finished | Call `speech_client.speak(_("Done"))` |
| Direct UI calls from threads | Thread contention, native crash | Wrap in `wx.CallAfter(...)` |
| Forgetting `_()` wrapping | Breaks internationalization for Arabic/other locales | Wrap all user text in `_()` |
| Over-speaking sliders | Floods TTS speech queue on rapid dragging | Speak only on key release or slider debounce |

## Verification & Quality Gates

- **Unit/Mock Testing**: Run `uv run pytest tests/test_comments_dialog.py tests/test_equalizer_dialog.py`
- **Lint Check**: Run `uv run ruff check src/gui/`
- **Manual Verification**:
  1. Launch app via `uv run src/accessible_youtube_downloader_pro.py`.
  2. Unplug/ignore mouse. Navigate entirely with Tab, Shift+Tab, Arrows, Space, Enter, Escape.
  3. Verify NVDA / JAWS / Windows Narrator announces each control name, value, and dialog title.
