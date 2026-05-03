# Equalizer Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Equalizer dialog (`EqualizerDialog`) with 10 frequency bands, 1 preamp slider, and preset management, integrated with the existing `EqualizerService` and `settings_handler`.

**Architecture:**
- Create `source/gui/equalizer_dialog.py` extending `wx.Dialog`.
- Use `wx.Slider` for frequency bands and preamp.
- `wx.Choice` for equalizer presets.
- Connect to `EqualizerService` for backend operations and `settings_handler` for persistence.
- Provide accessible labels using `wxPython` standards.

**Tech Stack:** Python, wxPython, VLC (via `EqualizerService`).

---

### Task 1: Create the Equalizer Dialog skeleton

**Files:**
- Create: `source/gui/equalizer_dialog.py`
- Test: `tests/test_gui_equalizer.py`

- [ ] **Step 1: Write skeleton code in `source/gui/equalizer_dialog.py`**

```python
import wx
from language_handler import _

class EqualizerDialog(wx.Dialog):
    def __init__(self, parent, equalizer_service):
        wx.Dialog.__init__(self, parent, title=_("Equalizer"))
        self.equalizer_service = equalizer_service
        self.SetSize(600, 400)
        self.Centre()
        
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Skeleton layout
        lbl = wx.StaticText(panel, -1, _("Equalizer Settings"))
        sizer.Add(lbl, 0, wx.ALL | wx.CENTER, 10)
        
        panel.SetSizer(sizer)
```

- [ ] **Step 2: Create a basic test in `tests/test_gui_equalizer.py`**

```python
import wx
import pytest
from gui.equalizer_dialog import EqualizerDialog
from media_player.equalizer import EqualizerService

@pytest.fixture
def app():
    return wx.App()

def test_equalizer_dialog_init(app):
    service = EqualizerService()
    dlg = EqualizerDialog(None, service)
    assert dlg.Title == "Equalizer"
    dlg.Destroy()
```

- [ ] **Step 3: Run the test**

Run: `pytest tests/test_gui_equalizer.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add source/gui/equalizer_dialog.py tests/test_gui_equalizer.py
git commit -m "feat: add equalizer dialog skeleton"
```

### Task 2: Implement UI sliders and controls

**Files:**
- Modify: `source/gui/equalizer_dialog.py`

- [ ] **Step 1: Add preamp and 10 band sliders**

```python
# In source/gui/equalizer_dialog.py, add to __init__
        self.bands = []
        # Create 10 bands + 1 preamp
        for i in range(11):
            slider = wx.Slider(panel, -1, 0, -20, 20, style=wx.SL_VERTICAL | wx.SL_LABELS)
            self.bands.append(slider)
            sizer.Add(slider, 0, wx.ALL, 5)
```

- [ ] **Step 2: Implement slider change event**

```python
# In source/gui/equalizer_dialog.py
    def on_slider_change(self, event):
        # Update preamp and bands based on index
        # 0 is preamp, 1-10 are bands
        # Use EqualizerService to update
        pass
```

- [ ] **Step 3: Commit**

```bash
git add source/gui/equalizer_dialog.py
git commit -m "feat: add equalizer sliders"
```

### Task 3: Integrate with persistence and service

**Files:**
- Modify: `source/gui/equalizer_dialog.py`

- [ ] **Step 1: Load/save settings using `settings_handler`**

```python
# In source/gui/equalizer_dialog.py
from settings_handler import config_get, config_set

# Use config_get("eq_preamp"), config_get("eq_bands") in __init__
# Use config_set when saving
```

- [ ] **Step 2: Connect service calls**

```python
# In source/gui/equalizer_dialog.py
# Use self.equalizer_service.set_preamp and set_band
```

- [ ] **Step 3: Commit**

```bash
git add source/gui/equalizer_dialog.py
git commit -m "feat: integrate equalizer with service and settings"
```

---

Plan complete and saved to `docs/superpowers/plans/2025-05-22-equalizer-dialog.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
