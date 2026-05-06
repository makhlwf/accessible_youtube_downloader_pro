# Enhance EqualizerService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the `EqualizerService` with a `get_preamp` method, more robust setting loading, and better test coverage.

**Architecture:** Add a simple getter for consistency, wrap configuration loading in error handling, and extend the test suite to cover edge cases and new functionality.

**Tech Stack:** Python, VLC (via python-vlc), pytest.

---

### Task 1: Add get_preamp() method

**Files:**
- Modify: `source/media_player/equalizer.py`
- Modify: `tests/test_equalizer.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_preamp():
    eq = EqualizerService()
    eq.set_preamp(10.0)
    assert eq.get_preamp() == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_equalizer.py::test_get_preamp -v`
Expected: FAIL with "AttributeError: 'EqualizerService' object has no attribute 'get_preamp'"

- [ ] **Step 3: Implement get_preamp()**

```python
    def get_preamp(self) -> float:
        """Get the current preamp level.

        Returns:
            Preamp value.
        """
        return self.preamp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_equalizer.py::test_get_preamp -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add source/media_player/equalizer.py tests/test_equalizer.py
git commit -m "feat: add get_preamp method to EqualizerService"
```

### Task 2: Robustness in load_settings

**Files:**
- Modify: `source/media_player/equalizer.py`
- Modify: `tests/test_equalizer.py`

- [ ] **Step 1: Write failing tests for invalid preamp settings**

```python
def test_load_settings_invalid_preamp():
    with patch("settings_handler.config_get") as mock_get:
        # Test non-numeric preamp
        mock_get.return_value = "invalid"
        eq = EqualizerService()
        eq.set_preamp(2.0) # Set a default first
        eq.load_settings()
        assert eq.preamp == 2.0 # Should remain unchanged if loading fails

        # Test out of range preamp
        mock_get.return_value = 30.0
        eq.load_settings()
        assert eq.preamp == 2.0 # Should remain unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_equalizer.py::test_load_settings_invalid_preamp -v`
Expected: FAIL (crash with ValueError or AssertionError if value is updated incorrectly)

- [ ] **Step 3: Robustify load_settings**

Wrap the preamp loading in `try...except`:

```python
    def load_settings(self) -> None:
        """Load equalizer settings from configuration."""
        import settings_handler

        preamp = settings_handler.config_get("eq_preamp")
        if preamp is not None:
            try:
                self.set_preamp(float(preamp))
            except (ValueError, TypeError):
                pass

        bands_str = settings_handler.config_get("eq_bands")
        # ... rest unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_equalizer.py::test_load_settings_invalid_preamp -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add source/media_player/equalizer.py tests/test_equalizer.py
git commit -m "fix: make load_settings robust against invalid preamp values"
```

### Task 3: Test unknown preset name in apply_preset

**Files:**
- Modify: `tests/test_equalizer.py`

- [ ] **Step 1: Write the test case**

```python
def test_apply_preset_unknown():
    eq = EqualizerService()
    with pytest.raises(ValueError, match="Unknown preset: NonExistent"):
        eq.apply_preset("NonExistent")
```

- [ ] **Step 2: Run test to verify it passes (as behavior already exists)**

Run: `pytest tests/test_equalizer.py::test_apply_preset_unknown -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_equalizer.py
git commit -m "test: add test case for unknown preset name in apply_preset"
```
