---
name: youtube-pot-security
description: >-
  Use when encountering YouTube 403 Forbidden errors, bot detection triggers,
  SABR streaming issues, or configuring PO token providers.
---

# YouTube PO Token & Bot Detection Circumvention

## Overview

YouTube actively employs automated bot detection and Proof of Origin (PO Token / Botguard) challenges to restrict programmatic access and throttle video stream URLs (resulting in HTTP 403 errors or broken playback). HexPlayer implements a multi-provider PO Token architecture in `src/pot_provider_service.py` supporting Deno, Node.js, and background HTTP generators to maintain uninterrupted playback and downloads.

## When to Use

- Encountering HTTP 403 Forbidden errors during playback or downloads.
- YouTube returns `Sign in to confirm you're not a bot` or SABR streaming limits.
- Configuring or debugging PO token providers in `src/pot_provider_service.py`.
- Working with `yt-dlp` getpot extractor plugins (`yt_dlp_plugins.extractor.getpot_*`).
- Managing provider registry lifecycles or resolving duplicate provider registration assertions.

**When NOT to use:**
- Standard UI styling or local database query modifications.

## Core Patterns & Invariants

### 1. Provider Registry Singleton Pattern
Providers must be registered once into `POT_PROVIDERS`. Multiple imports of `pot_provider_service.py` or re-running tests must not throw duplicate registration assertion errors:

```python
# ✅ REQUIRED: Guard against duplicate provider registration
def _register_in(
    provider_class: type, registry: dict[str, type], base_class: type = PoTokenProvider
):
    assert issubclass(provider_class, base_class), (
        f"{provider_class.__name__} must inherit from {base_class.__name__}"
    )
    if provider_class.PROVIDER_KEY in registry:
        return  # Prevent crash on module reloads or test runners
    registry[provider_class.PROVIDER_KEY] = provider_class
```

### 2. Token Caching & TTL Expiration
PO Tokens have limited lifespans. Cache tokens in memory with a timestamp and refresh them proactively before expiration (typically every 6 to 12 hours) to avoid blocking playback start:

```python
class CachedPoToken:
    def __init__(self, token: str, visitor_data: str, ttl_seconds: int = 21600):
        self.token = token
        self.visitor_data = visitor_data
        self.expires_at = time.time() + ttl_seconds

    def is_valid(self) -> bool:
        return time.time() < (self.expires_at - 300)  # 5-minute safety buffer
```

### 3. Provider Fallback Cascade
If the primary provider (e.g. `BgUtilHTTP`) fails or is unreachable, the system must cascade to secondary providers (`DenoBuiltin`, `NodeExternal`, `CustomHTTP`) rather than throwing an unhandled exception to the user.

## Quick Reference

| Provider Key | Mechanism | Requirements |
| :--- | :--- | :--- |
| `BgUtilHTTP` | Local/Remote HTTP server generating PO tokens | Running bgutil HTTP daemon |
| `DenoBuiltin` | Internal Deno script generating visitor data | `src/deno.exe` |
| `NodeExternal` | External Node.js script | Node.js in system `PATH` |
| `CustomHTTP` | Custom user-provided endpoint | Configured URL in settings |

## Implementation Procedures

### Step 1: Handling YouTube 403 in yt-dlp & MPV
1. Detect HTTP 403 or `format not available` in player or downloader.
2. Trigger PO Token regeneration via `get_pot_provider_service().get_token()`.
3. Pass updated `po_token` and `visitor_data` into extractor arguments:
   ```python
   ydl_opts["extractor_args"] = {
       "youtube": {"po_token": [f"web+{pot_token}"], "player_client": ["web", "mweb"]}
   }
   ```
4. Retry the request once with the newly generated token.

### Step 2: Testing Token Generation
Run targeted PO token tests:
```powershell
uv run pytest tests/test_pot_provider_service.py tests/test_pot_provider_ytdlp_integration.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Unconditional registry assertion | Crashes test suite on duplicate registration | Check `if key in registry: return` |
| Synchronous token generation on UI thread | Freezes UI for 2-5 seconds while solving challenge | Generate tokens in background thread |
| Hardcoding single user-agent | PO token signature mismatches UA, leading to immediate 403 | Keep User-Agent aligned with generator |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_pot_provider_service.py tests/test_pot_provider_settings.py`
- **Integration Tests**: Run `uv run pytest tests/test_pot_provider_ytdlp_integration.py`
- **Manual Verification**:
  1. Open Settings -> Advanced / PO Token settings.
  2. Test provider connection status.
  3. Verify a restricted video streams without HTTP 403 errors.
