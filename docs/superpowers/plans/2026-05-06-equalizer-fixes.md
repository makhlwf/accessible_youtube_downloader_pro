# Equalizer Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix saved settings application, add presets/reset, and optimize performance of the Equalizer.

**Architecture:** Refactor `EqualizerService` to be the single source of truth for loading, saving, and applying equalizer settings. Use a debounced update mechanism in the dialog to improve UI responsiveness.

**Tech Stack:** Python, wxPython, VLC (python-vlc).

---

### Task 1: Enhance EqualizerService with Presets and Storage Logic

**Files:**
- Modify: `source/media_player/equalizer.py`
- Test: `tests/test_equalizer.py`

- [ ] **Step 1: Write failing tests for presets and storage**

```python
def test_presets():
    eq = EqualizerService()
    eq.apply_preset("Rock")
    # Verify some band values for Rock
    assert eq.get_band(0) != 0.0

def test_load_save_settings():
    from settings_handler import config_set
    config_set("eq_bands", "1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0")
    config_set("eq_preamp", 5.0)
    eq = EqualizerService()
    eq.load_settings()
    assert eq.preamp == 5.0
    assert eq.get_band(0) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement presets and storage logic in EqualizerService**
- Add `PRESETS` dictionary with VLC values.
- Implement `get_band(index)`, `load_settings()`, `save_settings()`, `apply_preset(name)`, and `reset()`.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

### Task 2: Refactor EqualizerDialog with Reset and Debouncing

**Files:**
- Modify: `source/gui/equalizer_dialog.py`

- [ ] **Step 1: Add Reset button to the dialog**
- [ ] **Step 2: Implement debounced update**
- Use `wx.Timer` to delay `apply_to_player` calls by 100ms.
- [ ] **Step 3: Update storage logic to use eq_bands**
- Remove individual `band_N` config keys.
- [ ] **Step 4: Implement preset selection**
- Call `eq_service.apply_preset()` and update slider positions.
- [ ] **Step 5: Commit**

### Task 3: Simplify Player Initialization

**Files:**
- Modify: `source/media_player/player.py`

- [ ] **Step 1: Use eq_service.load_settings() in Player.__init__**
- [ ] **Step 2: Commit**

### Task 4: Add Shortcut and Menu Item to MediaGui

**Files:**
- Modify: `source/media_player/media_gui.py`

- [ ] **Step 1: Add Ctrl+E shortcut to AcceleratorTable**
- [ ] **Step 2: Add "Equalizer" item to "Track Options" menu**
- [ ] **Step 3: Implement onEqualizer handler**
- [ ] **Step 4: Commit**

### Task 5: Final Verification

- [ ] **Step 1: Verify settings persist across application restarts**
- [ ] **Step 2: Verify presets change sound correctly**
- [ ] **Step 3: Verify Reset button works**
- [ ] **Step 4: Verify Ctrl+E opens the dialog**
- [ ] **Step 5: Verify sliders are responsive**
