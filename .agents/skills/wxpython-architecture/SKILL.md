---
name: wxpython-architecture
description: >-
  Use when architecting wxPython desktop applications, designing sizer layouts,
  managing wx custom event loops, or structuring composite desktop controls.
---

# wxPython Desktop Architecture & Layout Engineering

## Overview

HexPlayer relies on **wxPython 4.3+** for native Windows graphical desktop controls. Effective wxPython architecture requires strict layout management using hierarchical sizers (never hardcoded pixel coordinates), decoupled event handling, custom event classes, and robust window lifecycle cleanup (`wx.EVT_CLOSE`).

## When to Use

- Constructing complex, responsive dialogs and panels with nested sizers in `src/gui/`.
- Creating custom event classes using `wx.lib.newevent.NewEvent()`.
- Managing window lifecycles, modal dialogs, and clean destruction via `wx.EVT_CLOSE`.
- Binding accelerator tables and global menu shortcuts.
- Debugging window layout clipping, sizer expansion, or resizing artifacts.

**When NOT to use:**
- Writing pure background data scraping or Deno RPC handling.

## Core Patterns & Invariants

### 1. Sizer-Only Layout Discipline
Never use absolute coordinates (`wx.Point`, `wx.Size` in constructors without sizers). Always use hierarchical sizers:

```python
# ✅ REQUIRED: Sizer hierarchy pattern
class SettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        label = wx.StaticText(self, wx.ID_ANY, _("General Settings"))
        main_sizer.Add(label, 0, wx.ALL, 8)
        
        # Grid sizer for aligned label-input pairs
        grid_sizer = wx.FlexGridSizer(rows=2, cols=2, vgap=6, hgap=10)
        grid_sizer.AddGrowableCol(1, 1)
        
        main_sizer.Add(grid_sizer, 1, wx.EXPAND | wx.ALL, 8)
        
        self.SetSizer(main_sizer)
        self.Layout()
```

### 2. Thread-Safe Custom Event Dispatching
When background threads need to notify wxPython components with complex data payloads, use `wx.lib.newevent`:

```python
import wx
import wx.lib.newevent

# Define custom event type and binder
SearchCompletedEvent, EVT_SEARCH_COMPLETED = wx.lib.newevent.NewEvent()

# Dispatched from worker thread:
event = SearchCompletedEvent(results=data, status="success")
wx.PostEvent(target_window, event)

# Handled on GUI thread:
self.Bind(EVT_SEARCH_COMPLETED, self._on_search_completed)
```

### 3. Graceful Window Destruction Lifecycle
Always bind `wx.EVT_CLOSE` to ensure background threads, media player handles, and timers are stopped before destroying window resources:

```python
def on_close(self, event):
    self._timer.Stop()
    self._stop_background_threads()
    self.Destroy()
```

## Quick Reference

| Sizer / Pattern | Usage |
| :--- | :--- |
| `wx.BoxSizer(wx.VERTICAL)` | Vertical stack of controls |
| `wx.BoxSizer(wx.HORIZONTAL)`| Horizontal row of controls |
| `wx.FlexGridSizer(rows, cols, vgap, hgap)` | Aligned form tables with growable columns |
| `sizer.Add(ctrl, 0, wx.ALL, 5)` | Add with padding, fixed size |
| `sizer.Add(ctrl, 1, wx.EXPAND \| wx.ALL, 5)` | Add with padding, expanding to fill available space |
| `self.SetSizerAndFit(sizer)` | Sets sizer and adjusts parent window to minimum fit |

## Implementation Procedures

### Step 1: Building a Two-Button Action Row
```python
btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
btn_sizer.AddStretchSpacer()

ok_btn = wx.Button(self, wx.ID_OK, _("OK"))
cancel_btn = wx.Button(self, wx.ID_CANCEL, _("Cancel"))

btn_sizer.Add(ok_btn, 0, wx.RIGHT, 6)
btn_sizer.Add(cancel_btn, 0)
main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
```

### Step 2: Registering Window Accelerator Tables
```python
entries = [
    wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("F"), self.ID_SEARCH),
    wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("D"), self.ID_DOWNLOAD),
]
accel_table = wx.AcceleratorTable(entries)
self.SetAcceleratorTable(accel_table)
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Absolute positioning (`wx.Point(50, 100)`) | Breaks on DPI scaling or Arabic text length | Use sizers exclusively |
| Missing `AddGrowableCol` on flex grids | Inputs remain tiny, failing to fill window | Specify `grid_sizer.AddGrowableCol(col, proportion)` |
| Destroying parent before children cancel | Access violation or dangling pointer | Stop child tasks before `Destroy()` |
| Hardcoded dialog dimensions | Text gets clipped when translated to longer languages | Use `SetSizerAndFit()` |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_comments_dialog.py tests/test_download_dialog.py`
- **Lint Check**: Run `uv run ruff check src/gui/`
- **Visual / Layout Check**: Test dialog under varying Windows display DPI scalings (100%, 125%, 150%).
