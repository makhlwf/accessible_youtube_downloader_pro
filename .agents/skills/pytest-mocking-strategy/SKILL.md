---
name: pytest-mocking-strategy
description: >-
  Use when writing, running, or fixing unit and integration tests,
  creating test fixtures, or mocking wxPython, MPV, Deno, or network services.
---

# Pytest Mocking Strategy & Quality Gates

## Overview

HexPlayer features a comprehensive automated test suite (365+ tests) in `tests/` designed to execute in headless CI environments (Windows/Linux runners) without physical displays, audio hardware, or internet connectivity. It achieves this through carefully isolated mocks in `tests/conftest.py` covering wxPython, `libmpv-2.dll`, Deno RPC streams, and YouTube network responses.

## When to Use

- Writing new unit or integration tests for features or bug fixes.
- Diagnosing test failures or mock leakages across test modules.
- Mocking wxPython GUI controls, dialogs, or event dispatchers.
- Simulating MPV playback events or Deno RPC responses in tests.
- Resolving pytest cache file collisions on Windows (`WinError 183`).

**When NOT to use:**
- Writing runtime application code without testing it.

## Core Patterns & Invariants

### 1. Headless wxPython Mocking Pattern
wxPython cannot create native Windows handles in headless CI runners. `tests/conftest.py` mounts a comprehensive `mock_wx` hierarchy into `sys.modules["wx"]`. When creating widgets in tests, use the mocked classes:

```python
# tests/conftest.py supplies mock_wx automatically
import wx


def test_dialog_initialization():
    parent = wx.Frame(None)
    dlg = MyDialog(parent)
    assert dlg.Parent is parent
```

### 2. Mocking Asynchronous Media & Deno Calls
Never perform live network requests in unit tests. Use `unittest.mock.patch` or monkeypatching on `deno_service` and `mpv_backend`:

```python
def test_search_processing(monkeypatch):
    mock_results = [{"id": "xyz", "title": "Test Video"}]
    monkeypatch.setattr(
        "deno_service.get_deno_service",
        lambda: MagicMock(search=MagicMock(return_value=mock_results)),
    )
    # Execute test logic against mock
```

### 3. Pytest Cache Path Safety on Windows
On Windows, concurrent processes or permission locks may trigger:
`PytestCacheWarning: could not create cache path ... [WinError 183] Cannot create a file when that file already exists`
To execute tests cleanly without cache warnings when needed, use `-p no:cacheprovider`:

```powershell
uv run pytest -p no:cacheprovider tests/
```

### 4. Test Isolation
Every test must leave global state clean. Any monkeypatched attributes or database connections in temporary directories must be torn down via fixtures:

```python
@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(db_file)
    yield db
    db.close()
```

## Quick Reference

| Test Target | Recommended Command |
| :--- | :--- |
| **Full Test Suite** | `uv run pytest tests/` |
| **Single Module** | `uv run pytest tests/test_downloader.py` |
| **Fast Run (No Cache)** | `uv run pytest -p no:cacheprovider tests/` |
| **Verbose Output** | `uv run pytest -ra -vv tests/` |
| **Linter Verification** | `uv run ruff check .` |

## Implementation Procedures

### Step 1: Adding a Test for a New Dialog
1. Create `tests/test_<feature>_dialog.py`.
2. Instantiate the dialog using a mocked parent frame.
3. Simulate user interactions by directly calling event handlers or inspecting widget values:
   ```python
   def test_submit_button_triggers_action(monkeypatch):
       called = []
       monkeypatch.setattr("utils.perform_action", lambda: called.append(True))
       dlg = FeatureDialog(None)
       dlg.on_submit(None)
       assert called == [True]
   ```
4. Run pytest against the new module to verify passes.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Attempting to instantiate real `wx.App` in headless test | Segmentation fault or native crash | Use `mock_wx` from `conftest.py` |
| Live internet calls in tests | Flaky tests on network blips / CI timeouts | Mock HTTP and Deno RPC calls |
| Leaking monkeypatches across tests | Causes mysterious failures in subsequent tests | Use pytest's `monkeypatch` fixture |
| Ignoring lint errors | Fails pre-commit and CI | Run `uv run ruff check .` before committing |

## Verification & Quality Gates

- **Full Suite Run**: Run `uv run pytest tests/`
- **Lint Check**: Run `uv run ruff check tests/`
- **Result Verification**: All 365+ tests must pass with 0 failures.
