---
name: desktop-a11y-specialist
description: >-
  Use when designing, auditing, or debugging Windows accessibility APIs,
  UI Automation (UIA) trees, MSAA/IAccessible2 fallback, accessible control naming, or high contrast themes.
---

# Windows Desktop Accessibility & Platform APIs

## Overview

HexPlayer operates on Windows where assistive technologies (NVDA, JAWS, Narrator, SuperNova) consume accessibility trees via **UI Automation (UIA)** and legacy **MSAA / IAccessible2**. Every control must reliably expose Name, Role, Value, and State (NRVS) so blind users receive accurate verbal and braille representations of UI elements.

## When to Use

- Auditing or improving accessibility metadata (Name, Role, Value, State) for custom controls in `src/gui/`.
- Inspecting the UIA element hierarchy with Windows SDK `inspect.exe` or Accessibility Insights.
- Designing custom widgets that require explicit MSAA/UIA property overrides.
- Supporting Windows High Contrast Mode themes and system color query hooks.
- Ensuring screen readers recognize composite components (e.g. search suggestions, timecode lists).

**When NOT to use:**
- Writing web applications or handling browser DOM/HTML/CSS (HexPlayer is a native wxPython desktop app).

## Core Patterns & Invariants

### 1. Name, Role, Value, State (NRVS) Discipline
Every interactive or informational element must satisfy all four properties:

```python
# ✅ REQUIRED: Explicitly define Name and Role for controls
class AccessibleStatusPanel(wx.Panel):
    def __init__(self, parent, label_text: str):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(label_text)  # UIA 'Name' property
        # Set accessible role or label using wx.Accessible if custom
```

### 2. Sizer-Driven Logical Tab Order
The tab sequence on Windows mirrors the sizer hierarchy:
- Top-to-bottom, left-to-right logical ordering.
- Never insert controls outside sizers or rely on absolute pixel positioning (`wx.Point(x, y)`).
- Ensure hidden controls (`Show(False)`) are removed from active tab traversal so screen readers do not focus invisible phantoms.

### 3. Windows High Contrast Mode Detection
Never hardcode RGB background and foreground colors. Always check system high contrast settings:

```python
import wx


def is_high_contrast_active() -> bool:
    return wx.SystemSettings.GetMetric(wx.SYS_HIGHCONTRAST_ON) != 0


def apply_accessible_colors(window: wx.Window):
    if is_high_contrast_active():
        window.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        window.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        )
```

## Quick Reference

| UIA Property | wxPython Counterpart | Verification |
| :--- | :--- | :--- |
| **Name** | `control.SetName(text)` / `SetLabel(text)` | Announced when control gains focus |
| **Role** | Control class type (`wx.Button`, `wx.Choice`) | Screen reader announces "button", "combo box" |
| **Value** | `control.GetValue()` / `GetStringSelection()` | Announced upon selection change |
| **State** | `IsEnabled()`, `IsChecked()`, `HasFocus()` | "Unavailable", "Checked", "Focused" |

## Implementation Procedures

### Step 1: Making a Custom Control Fully Accessible
1. Subclass `wx.Panel` with `wx.TAB_TRAVERSAL`.
2. Provide a descriptive accessible name:
   ```python
   self.SetName(_("Volume Slider"))
   ```
3. Bind keyboard handlers (`wx.EVT_KEY_DOWN`) for standard interactions.
4. When state changes, announce through `speech_client.speak`.

### Step 2: Verifying with Windows Accessibility Insights
1. Launch HexPlayer: `uv run src/accessible_youtube_downloader_pro.py`.
2. Open **Accessibility Insights for Windows**.
3. Hover or tab to the window and check the UIA tree inspection panel.
4. Verify that `AutomationId`, `Name`, `ControlType`, and `LocalizedControlType` are populated.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Icon-only buttons with empty labels | Screen reader announces "Button" with no name | Always supply `label` or `SetName(_("..."))` |
| Using Web ARIA rules on desktop | Desktop has no DOM or ARIA attributes | Use native wxPython and UIA APIs |
| Hardcoded dark/light palette | Unreadable in Windows High Contrast Mode | Query `wx.SystemSettings.GetColour(...)` |
| Floating widgets without sizers | Breaks keyboard tab order | Place all widgets in hierarchical sizers |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_custom_controls.py tests/test_theme_handler.py`
- **Lint Check**: Run `uv run ruff check src/gui/`
- **Manual Verification**:
  1. Turn on Windows High Contrast Mode (`Left Alt + Left Shift + PrintScreen`).
  2. Launch HexPlayer and verify text contrast and borders are clear.
  3. Inspect controls with Windows SDK `inspect.exe`.
