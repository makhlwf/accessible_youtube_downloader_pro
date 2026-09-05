---
name: windows-build-packaging
description: >-
  Use when building the standalone Windows executable,
  resolving binary DLL dependencies, updating Inno Setup installer scripts, or generating release metadata.
---

# Windows Binary Packaging & Inno Setup Engine

## Overview

HexPlayer compiles into standalone Windows binaries using **PyInstaller** (`scripts/build.py`, `HexPlayer.spec`) and packages into a production Windows installer via **Inno Setup** (`packaging/windows/inno.iss`). It packages two separate executables: `HexPlayer.exe` (windowed desktop application) and `HexPlayerNativeHost.exe` (console stdio host for the Chrome extension), bundling all required media engines and system DLLs.

## When to Use

- Executing or modifying the application compilation pipeline in `scripts/build.py`.
- Adjusting binary file dependencies, hidden imports, or assets in `HexPlayer.spec`.
- Modifying installer registry entries, shortcuts, or file associations in `packaging/windows/inno.iss`.
- Resolving missing runtime DLL issues (`libmpv-2.dll`, `ffmpeg.exe`, `vulkan-1.dll`).
- Updating release update manifests (`update.json`, `update_info.json`) for the in-app updater.

**When NOT to use:**
- Writing pure application feature logic or tests.

## Core Patterns & Invariants

### 1. Dual-Target PyInstaller Compilation
The build script generates two executables:
1. `HexPlayer.exe`: Windowed executable (`console=False`), main UI app.
2. `HexPlayerNativeHost.exe`: Console executable (`console=True`), stdio Native Messaging Host for Chromium browsers.

### 2. Runtime Binary Bundling
The following binaries MUST be present and bundled into the distribution directory:
- `libmpv-2.dll` (extracted from `src/libmpv-2.dll.zip` if not extracted)
- `ffmpeg.exe` and `ffprobe.exe` (in `src/`)
- `deno.exe` (in `src/`)
- System libraries: `vulkan-1.dll` (resolved from `System32` or system `PATH`)

```python
# scripts/build.py validates DLL existence before building
REQUIRED_BINARIES = [
    "libmpv-2.dll",
    "ffmpeg.exe",
    "ffprobe.exe",
    "deno.exe",
]
```

### 3. Inno Setup Registry & Protocol Binding
The installer compiler script (`packaging/windows/inno.iss`) configures:
- The `hexplayer://` custom URI scheme in `HKCU\Software\Classes\hexplayer`.
- The Chrome/Edge Native Messaging Host registry keys.
- Start Menu and Desktop shortcuts with proper accessibility flags.

### 4. Release Update Manifests
When releasing a new version:
1. Bump `version` in `pyproject.toml`.
2. Update `update.json` and `update_info.json` with new version string, release notes, and download URLs.

## Quick Reference

| Action | Command |
| :--- | :--- |
| **Run PyInstaller Build** | `uv run python scripts/build.py` |
| **Full Build & Package** | `.\BuildNPackage.bat` |
| **Compile Installer Only**| `iscc packaging\windows\inno.iss` |
| **Release Manifests** | `update.json`, `update_info.json` |

## Implementation Procedures

### Step 1: Performing a Production Build
1. Run preflight checks: `uv run python scripts/agent_preflight.py`.
2. Execute the build script:
   ```powershell
   uv run python scripts/build.py
   ```
3. Verify that `dist/HexPlayer/HexPlayer.exe` and `dist/HexPlayer/HexPlayerNativeHost.exe` are generated.
4. If Inno Setup (`iscc`) is installed, compile the installer:
   ```powershell
   .\BuildNPackage.bat
   ```

### Step 2: Verifying Bundled Binary Health
Verify that all runtime DLLs are present in the output folder:
```powershell
uv run pytest tests/test_runtime_dlls.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Setting `console=False` for NativeHost | Chrome cannot open stdio pipes; host crashes | NativeHost must have `console=True` |
| Forgetting `vulkan-1.dll` | MPV hardware video decoding fails on some GPUs | Copy from System32 in `build.py` |
| Hardcoding developer paths in `inno.iss` | Breaks compilation on other build machines | Use relative paths `{app}` |
| Skipping preflight before building | Bundles broken code or out-of-sync translations | Run `agent_preflight.py` first |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_runtime_dlls.py`
- **Build Execution**: Run `uv run python scripts/build.py --dry-run` (or full build)
- **Output Inspection**: Ensure `dist/HexPlayer/` contains required DLLs and executables.
