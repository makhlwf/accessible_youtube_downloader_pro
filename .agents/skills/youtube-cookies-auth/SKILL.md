---
name: youtube-cookies-auth
description: >-
  Use when configuring or debugging YouTube cookie extraction from web browsers,
  Windows DPAPI decryption, or age-restricted and YouTube Premium playback.
---

# YouTube Cookie Extraction & Authenticated Sessions

## Overview

HexPlayer features a browser cookie extraction engine (`src/cookies_manager.py`) enabling blind users to access their YouTube account data, subscribed channels, liked videos, private playlists, age-restricted media, and YouTube Premium high-bitrate audio streams without manually managing tokens or typing complex passwords.

## When to Use

- Extracting YouTube cookies from Chromium browsers (Chrome, Edge, Brave, Opera, Vivaldi) or Mozilla Firefox.
- Resolving Windows DPAPI (`CryptUnprotectData`) or AES-256-GCM `v10` cookie decryption failures.
- Handling browser SQLite file locking (`database is locked` when browser is currently open).
- Passing authenticated cookie sessions to `yt-dlp` or Deno's YouTube.js InnerTube bridge.
- Debugging session expiration, cookie validation, or age-restricted video playback blocks.

**When NOT to use:**
- Handling PO token Proof of Origin challenges (use `youtube-pot-security`).

## Core Patterns & Invariants

### 1. Browser Database Copying to Avoid File Locks
When a user has their web browser open, Windows places exclusive file locks on the browser's `Cookies` SQLite database. Never attempt to read the database directly in-place:

```python
# ✅ REQUIRED: Copy cookie database to temp directory before connecting
import tempfile
import shutil
import sqlite3


def open_browser_cookie_db(source_db_path: Path):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        temp_path = Path(tmp.name)
    shutil.copy2(source_db_path, temp_path)
    return sqlite3.connect(temp_path), temp_path
```

### 2. Windows DPAPI & AES-256-GCM Decryption Protocol
Chromium stores cookies encrypted. On Windows:
1. Read the encrypted master key from `User Data\Local State`.
2. Strip the `DPAPI` prefix (5 bytes).
3. Decrypt the master key using `win32crypt.CryptUnprotectData` (or `ctypes.windll.crypt32.CryptUnprotectData`).
4. Read encrypted cookie value: if prefixed with `v10` (3 bytes), the next 12 bytes are the AES-GCM IV/nonce, followed by ciphertext and 16-byte authentication tag.
5. Decrypt using AES-GCM with the decrypted master key.

### 3. Netscape Cookie Export Format
Both `yt-dlp` and HTTP clients accept standard Netscape-formatted cookie files (`cookies.txt`):

```
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	1798765432	LOGIN_INFO	AFmmF2sw...
.youtube.com	TRUE	/	TRUE	1798765432	SAPISID	xyz123...
```

### 4. Zero Credential Exposure Invariant
Never print decrypted session tokens or cookie values to application log files or console output. Only verify boolean presence of `LOGIN_INFO` or `SAPISID`.

## Quick Reference

| Browser | Cookie Database Location |
| :--- | :--- |
| **Google Chrome** | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies` |
| **Microsoft Edge** | `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Network\Cookies` |
| **Brave Browser** | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies` |
| **Mozilla Firefox**| `%APPDATA%\Mozilla\Firefox\Profiles\<profile>\cookies.sqlite` |

## Implementation Procedures

### Step 1: Extracting Cookies from Selected Browser
1. In Settings -> Accounts/Cookies, user selects browser (e.g. Chrome).
2. Call `cookies_manager.extract_cookies_from_browser("chrome")`.
3. Verify presence of essential authentication keys (`LOGIN_INFO`, `HSID`, `SSID`, `APISID`, `SAPISID`).
4. Save exported cookiejar to `%APPDATA%\HexPlayer\cookies.txt`.
5. Announce status:
   ```python
   speech_client.speak(
       _("YouTube cookies extracted successfully from {browser}.").format(browser="Chrome")
   )
   ```

### Step 2: Injecting Cookies into yt-dlp & Deno
- **yt-dlp**: Add `ydl_opts["cookiefile"] = str(paths.get_cookies_path())`.
- **Deno**: Read cookies file and pass cookie string in headers to `service.js`.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Opening browser db directly | Fails with `sqlite3.OperationalError: database is locked` | Copy to temp file first |
| Printing cookies to logs | Security vulnerability (token leakage) | Strip or mask cookie values |
| Assuming cookies never expire | Auth silently drops after weeks | Handle auth errors and prompt refresh |
| Hardcoding Chrome default profile | Users may use "Profile 1", "Profile 2" | Scan all profile subdirectories |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_cookies_manager.py`
- **Lint Check**: Run `uv run ruff check src/cookies_manager.py`
- **Manual Verification**:
  1. Open Settings -> Cookies.
  2. Select installed browser and click "Import Cookies".
  3. Verify success speech announcement and test opening a private playlist.
