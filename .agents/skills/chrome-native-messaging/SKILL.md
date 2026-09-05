---
name: chrome-native-messaging
description: >-
  Use when working on the Chrome/Brave/Edge browser extension,
  Manifest V3 service worker, native messaging IPC protocol, or the hexplayer:// URL scheme.
---

# Chromium Extension & Native Messaging Host

## Overview

HexPlayer integrates with modern Chromium browsers (Chrome, Edge, Brave) via a Manifest V3 browser extension and a standard **Native Messaging Host** executable (`src/native_messaging_host.py`). This allows blind users browsing YouTube in their web browser to press a context menu hotkey or click the extension to immediately transfer the video, playlist, or timestamp to HexPlayer.

## When to Use

- Updating or debugging the Chromium extension in `src/browser_extension/` (`manifest.json`, `background.js`).
- Modifying or fixing the stdio binary native messaging protocol in `src/native_messaging_host.py`.
- Managing Windows Registry entries for native hosts or the `hexplayer://` protocol handler.
- Handling URL sanitization, command-line arguments, or browser-to-desktop handoffs.

**When NOT to use:**
- In-app media playback or download logic unrelated to browser input.

## Core Patterns & Invariants

### 1. 4-Byte Little-Endian Binary Stdio Framing
Native messaging communicates across stdio using a 32-bit unsigned integer prefix specifying message byte length:

```python
# ✅ REQUIRED: Read 4-byte little-endian length prefix
raw_length = sys.stdin.buffer.read(4)
if not raw_length:
    sys.exit(0)
message_length = struct.unpack("@I", raw_length)[0]
message_bytes = sys.stdin.buffer.read(message_length)
message = json.loads(message_bytes.decode("utf-8"))

# Send response back to browser:
encoded_response = json.dumps(response).encode("utf-8")
sys.stdout.buffer.write(struct.pack("@I", len(encoded_response)))
sys.stdout.buffer.write(encoded_response)
sys.stdout.buffer.flush()
```

### 2. URL Scheme Sanitization
Incoming URLs from `hexplayer://` or native messaging must be validated strictly against YouTube URL patterns before launching player actions, preventing arbitrary command injection:

```python
from youtube_url_utils import is_valid_youtube_url

if not is_valid_youtube_url(url):
    raise ValueError(f"Untrusted or invalid YouTube URL: {url}")
```

### 3. Windows Registry Host Manifest Registration
The host JSON manifest (`com.hexplayer.native_host.json`) must be registered in the current user's registry:
- Chrome: `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.hexplayer.native_host`
- Edge: `HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.hexplayer.native_host`
- Brave: `HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.hexplayer.native_host`

The default value must point to the absolute path of the manifest JSON file.

### 4. Manifest V3 Service Worker Lifecycle
Chrome MV3 service workers can terminate after 30 seconds of inactivity. `background.js` must reconnect native messaging ports upon user action:

```javascript
// background.js
chrome.contextMenus.onClicked.addListener((info, tab) => {
    const port = chrome.runtime.connectNative('com.hexplayer.native_host');
    port.postMessage({ action: 'play', url: info.linkUrl || info.pageUrl });
    port.onDisconnect.addListener(() => {
        if (chrome.runtime.lastError) {
            console.error("Native host disconnected:", chrome.runtime.lastError.message);
        }
    });
});
```

## Quick Reference

| Component | Path / Registry Key |
| :--- | :--- |
| **Native Host Script** | `src/native_messaging_host.py` |
| **Compiled Host Exe** | `HexPlayerNativeHost.exe` |
| **Chrome Manifest Key**| `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.hexplayer.native_host` |
| **Protocol Handler Key**| `HKCU\Software\Classes\hexplayer` |
| **Extension Folder** | `src/browser_extension/` |

## Implementation Procedures

### Step 1: Registering Native Host in Windows Registry
1. Generate the JSON manifest file pointing to `HexPlayerNativeHost.exe`.
2. Open registry key `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.hexplayer.native_host` with `winreg.KEY_SET_VALUE`.
3. Set default string value to the manifest path.
4. Repeat for Microsoft Edge and Brave Browser keys.

### Step 2: Testing Native Host Communication
Run the dedicated automated IPC test:
```powershell
uv run pytest tests/test_native_messaging_host.py tests/test_windows_url_association.py
```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Writing debug `print()` to stdout in host | Corrupts binary framing; Chrome drops connection | Write debug output to `sys.stderr` or file |
| Missing `sys.stdout.buffer.flush()` | Messages buffered; Chrome times out | Always flush immediately after writing |
| Passing unsanitized URLs to `os.system` | Remote code execution vulnerability | Use `subprocess.Popen([exe, url])` |
| Forgetting little-endian `@I` pack | Corrupts length header on 64-bit systems | Use `struct.pack('@I', len)` |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_native_messaging_host.py tests/test_windows_url_association.py`
- **Lint Check**: Run `uv run ruff check src/native_messaging_host.py src/windows_url_association.py`
- **Manual Verification**:
  1. Open Chrome with extension unpacked from `src/browser_extension/`.
  2. Right-click on a YouTube video and choose "Play in HexPlayer".
  3. Verify HexPlayer launches and begins playback immediately.
