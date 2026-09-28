---
last_mapped_commit: aa0548eb54ee3fe3f2265d041a55a96ee9a81121
last_mapped_at: 2026-09-28
---
# Testing Patterns

**Analysis Date:** 2026-09-28

## Test Framework

**Runner:**
- pytest (`pytest>=9.0.2,<10`, dev group in `pyproject.toml`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml` — `testpaths = ["tests"]`, `pythonpath = ["src"]`, `addopts = "-ra"`.

**Async:**
- `pytest-asyncio>=1.3.0` is installed. No global `asyncio_mode` is set, so async coroutines are driven manually where needed (`tests/test_suggestions_service.py` builds its own `asyncio.get_event_loop()`); most async collaborators are mocked with `MagicMock`/`AsyncMock`.

**Assertion Library:**
- Plain `assert` statements (pytest rewriting). `pytest.raises` for exception paths.

**Run Commands:**

```bash
uv run pytest tests/                 # Run all tests
uv run pytest tests/test_downloader.py   # Single module
uv run pytest -k download            # Filter by name
uv run python scripts/agent_preflight.py  # Full gate: skills + ruff + translations + pytest
```

## Test File Organization

**Location:**
- Separate top-level `tests/` directory (not co-located with `src/`).

**Naming:**
- `test_<subject>.py`, mirroring source modules (`test_downloader.py` ↔ `download_handler/downloader.py`, `test_pot_provider_service.py` ↔ `pot_provider_service.py`).

**Structure:**

```
tests/
├── conftest.py          # Global wx mock, sys.path setup, autouse fixtures
├── test_downloader.py
├── test_settings.py
├── test_pot_provider_*.py   # service / settings / ui / e2e / ytdlp_integration split
├── test_media_gui_*.py      # GUI behavior slices
└── ... (~55 test modules)
```

## Test Structure

**Style:** Predominantly module-level `def test_*` functions (function-per-behavior), not `unittest.TestCase` classes. Names describe the scenario and expectation.

```python
def test_audio_download_format_falls_back_when_converting_to_mp3():
    downloader = Downloader("url", ".", "bestaudio[ext=m4a]", None, None, convert=True)
    assert get_audio_download_format(convert=True) == "bestaudio/best"
    assert downloader._effective_format() == "bestaudio/best"

def test_progress_hook_raises_when_cancelled():
    downloader = Downloader("url", ".", "best", None, None, cancel_checker=lambda: True)
    with pytest.raises(DownloadCancelled):
        downloader._progress_hook({"status": "downloading"})
```

**Patterns:**
- `monkeypatch` is the primary isolation tool — patch module attributes (`monkeypatch.setattr(paths, "ffmpeg_dir", ...)`), env vars (`monkeypatch.setenv`), and config accessors (`config_get`).
- `tmp_path` fixture for filesystem paths; assertions normalize with `os.path.normpath`.
- Pure format/parsing helpers are tested directly against expected strings (no I/O).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `monkeypatch` from pytest). No `pytest-mock` plugin.

**wxPython is mocked wholesale in `tests/conftest.py`:**

```python
sys.modules["wx"] = mock_wx        # hand-built fake wx with Frame/Panel/Dialog/
sys.modules["wx.adv"] = MagicMock()  #   TextCtrl/ListBox/Choice/Slider/CheckBox...
```

`conftest.py` defines lightweight fake widget classes (`wxWindow` base with `Show/Hide/Enable/SetFocus`, plus `ListBox`, `Choice`, `Slider`, `MockTimer`, `Point`, `Size`) and stub wx constants, so GUI modules import and run headlessly without a display.

Other heavy externals are stubbed the same way: `py_yt` (search/playlist classes via `MockType` metaclass), `pyperclip`.

**Autouse fixtures (`conftest.py`):**
- `reset_gettext` — sets `builtins._` to an identity function so `_()` works without a catalog.
- `mock_speech_backend` — replaces the `speech_client` prism backend with a `MagicMock` (unless `HEXPLAYER_TEST_LIVE_SPEECH=1`).
- `mock_audio_devices` — patches `mpv_backend.get_available_audio_output_devices` to a fixed device list.

**What to Mock:**
- wx GUI, speech backend, audio devices, network/search (`py_yt`), clipboard, subprocess-backed runtimes.

**What NOT to Mock:**
- Pure logic under test (format selection, URL parsing, progress-text cleaning) — exercised directly.

## Fixtures and Factories

- Built-in pytest fixtures (`tmp_path`, `monkeypatch`) plus the autouse fixtures above. No dedicated factory library; test objects are constructed inline (`Downloader(...)`).

## Coverage

**Requirements:** None enforced (no `coverage`/`pytest-cov` in deps, no threshold in CI). Breadth is achieved via ~55 focused test modules.

## Test Types

**Unit tests:** The bulk — pure helpers and class methods with mocked collaborators.

**GUI behavior tests:** `test_media_gui_*.py`, `test_*_dialog.py` — drive fake-wx widgets to assert accessibility/behavior (focus, selection, key handling).

**Integration / live tests:** Gated behind the `integration` marker and env flags so they are skipped by default:

```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("HEXPLAYER_TEST_LIVE_POT") != "1",
        reason="Set HEXPLAYER_TEST_LIVE_POT=1 to run the live network/POT test",
    ),
]
```

The `integration` marker is registered in `pytest_configure` (`conftest.py`). Related env gates: `HEXPLAYER_TEST_LIVE_SPEECH`, `HEXPLAYER_TEST_LIVE_POT`, `POT_TEST_DIR`.

**E2E:** `test_pot_provider_e2e.py`, `test_linux_gui_integration.py` — live binaries/hardware, opt-in only.

## Common Patterns

**Error/exception testing:**

```python
with pytest.raises(DownloadCancelled):
    downloader._progress_hook({"status": "downloading"})
```

**Config/path isolation:**

```python
monkeypatch.setattr(downloader_module, "config_get", lambda key: "1" if key == "conversion" else "")
monkeypatch.setattr(paths, "ffmpeg_dir", str(tmp_path / "system-bin"))
monkeypatch.setenv("PATH", "")
```

## CI Integration

- `.github/workflows/tests.yml` runs the suite; `lint.yml` and `translations_check.yml` enforce ruff and catalog freshness.
- Locally, `scripts/agent_preflight.py` is the mandatory gate (skills validator → `ruff check .` → `scripts/check_translations.py` → `pytest tests/`) before claiming completion.
- Pre-commit runs `ruff check --fix` and `ruff format`; pre-push adds CI-style ruff checks and `scripts/check_translations.py`.

---

*Testing analysis: 2026-09-28*
