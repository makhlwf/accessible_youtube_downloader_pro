# Equalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a fully accessible, persistent 10-band equalizer for the media player with live update capability.

**Architecture:**
- Create an `EqualizerService` wrapper around `vlc.AudioEqualizer`.
- Persist settings via `settings_handler.py`.
- New UI `EqualizerDialog` with live slider updates.

**Tech Stack:** Python, wxPython, python-vlc.

---

### Task 1: Setup Equalizer Backend Service

**Files:**
- Create: `source/media_player/equalizer.py`
- Test: `tests/test_equalizer.py`

- [ ] **Step 1: Write initial test for Equalizer service**

```python
import pytest
from media_player.equalizer import EqualizerService

def test_equalizer_init():
    eq = EqualizerService()
    assert eq.equalizer is not None

def test_preamp_setting():
    eq = EqualizerService()
    eq.set_preamp(5.0)
    # VLC doesn't expose a simple getter for current preamp easily, 
    # but we can verify our internal state
    assert eq.preamp == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_equalizer.py`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
import vlc

class EqualizerService:
    def __init__(self):
        self.equalizer = vlc.AudioEqualizer()
        self.preamp = 0.0

    def set_preamp(self, value):
        self.preamp = value
        self.equalizer.set_preamp(value)

    def set_band(self, index, value):
        self.equalizer.set_amp_at_index(value, index)

    def apply_to_player(self, player):
        player.set_equalizer(self.equalizer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_equalizer.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add source/media_player/equalizer.py tests/test_equalizer.py
git commit -m "feat: create equalizer backend service"
```

### Task 2: Settings Persistence Integration

**Files:**
- Modify: `source/settings_handler.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Write test for new settings**

```python
from settings_handler import config_get, config_set

def test_eq_settings():
    config_set("eq_enabled", True)
    assert config_get("eq_enabled") is True
```

- [ ] **Step 2: Update `defaults` in `source/settings_handler.py`**

```python
# Add to defaults dictionary in settings_handler.py
    "eq_enabled": False,
    "eq_preamp": 0.0,
    "eq_bands": "0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0",
    "eq_preset": "Flat",
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_settings.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add source/settings_handler.py tests/test_settings.py
git commit -m "feat: add equalizer settings to configuration"
```

### Task 3: Equalizer GUI Implementation

**Files:**
- Create: `source/gui/equalizer_dialog.py`

- [ ] **Step 1: Implement `EqualizerDialog` UI**

```python
import wx
from media_player.equalizer import EqualizerService
from settings_handler import config_get, config_set

class EqualizerDialog(wx.Dialog):
    def __init__(self, parent, player):
        super().__init__(parent, title="Equalizer")
        self.player = player
        self.eq_service = EqualizerService()
        self.init_ui()

    def init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Create 10 band sliders + Preamp slider
        # ... UI logic ...
        self.SetSizer(sizer)

    def on_slider_change(self, event):
        # Update eq_service and player immediately
        pass
```

- [ ] **Step 2: Commit**

```bash
git add source/gui/equalizer_dialog.py
git commit -m "feat: implement equalizer UI dialog"
```

### Task 4: Integration with Player

**Files:**
- Modify: `source/media_player/player.py`

- [ ] **Step 1: Update `Player` class to use `EqualizerService`**

```python
# In Player.__init__
if config_get("eq_enabled"):
    self.eq = EqualizerService()
    # load bands from config
    self.eq.apply_to_player(self.media)
```

- [ ] **Step 2: Commit**

```bash
git add source/media_player/player.py
git commit -m "feat: integrate equalizer with media player"
```
