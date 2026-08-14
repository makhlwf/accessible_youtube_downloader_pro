<h1 align="center">HexPlayer</h1>

<p align="center">
  <a href="https://github.com/makhlwf/accessible_youtube_downloader_pro/releases" aria-label="GitHub release page">
    <img src="https://img.shields.io/github/v/release/makhlwf/accessible_youtube_downloader_pro?style=for-the-badge&color=blue"
         alt="GitHub release version badge" />
  </a>

  <a href="https://www.python.org/" aria-label="Python official website">
    <img src="https://img.shields.io/badge/Python-3.14+-brightgreen?style=for-the-badge&logo=python"
         alt="Python version 3.14 or higher" />
  </a>

  <a href="https://www.microsoft.com/windows" aria-label="Microsoft Windows website">
    <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows"
         alt="Platform Windows" />
  </a>

  <a href="https://en.wikipedia.org/wiki/Web_Accessibility" aria-label="Accessibility information">
    <img src="https://img.shields.io/badge/Accessibility-Screen%20Reader%20Friendly-orange?style=for-the-badge"
         alt="Screen reader friendly accessibility badge" />
  </a>

  <a href="https://www.gnu.org/licenses/gpl-3.0" aria-label="GPL v3 license">
    <img src="https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge"
         alt="License GPL version 3" />
  </a>
</p>

<p align="center">
  <b>HexPlayer</b> is an accessible Windows application for searching, browsing, watching, and downloading YouTube content with a keyboard-first interface.
</p>

---

## Overview

HexPlayer is the current continuation of Accessible YouTube Downloader Pro. It is designed for blind and visually impaired Windows users who want a screen-reader friendly way to use YouTube without relying on the YouTube web interface. HexPlayer works with all Windows screen readers (NVDA, JAWS, Narrator, System Access, etc.) and Windows speech engines via [Prism](https://github.com/ethindp/prism).

The current application version is **4.1.0**. The app is intended for modern 64-bit Windows systems, especially Windows 10 and Windows 11.

---

## Key Features

- **YouTube search and browsing:** Search videos, playlists, channels, and live content directly inside the app.
- **YouTube Shorts Experience:** Browse YouTube Shorts recommendations seamlessly with dedicated `Up`/`Down` navigation, background stream preloading for zero-buffering playback, continuous native looping, and context-aware actions like Liking, Disliking, and Commenting (requires cookies file).
- **Playlist and channel views:** Open playlists and browse channel tabs such as videos, shorts, live streams, playlists, community, channels, and about.
- **Accessible media player:** Play content as video or audio-only with keyboard shortcuts, volume boost, playback speed control, chapters, quality switching, equalizer, and audio output device selection.
- **Downloads:** Download videos, playlists, channels, Shorts, and supported YouTube links as MP4, M4A, or MP3 using `yt-dlp`.
- **Quality selection:** Choose available video quality before video downloads, and configure default playback quality.
- **Favorites:** Save local favorite videos and quickly play or download them later.
- **Account features:** Import YouTube cookies automatically from installed browsers, export directly with 1 click from the HexPlayer browser extension, or use a custom cookies file for YouTube Shorts recommendations, account watch history, home feed recommendations, likes, chapters, comment posting, and signed-in content.
- **Resume playback:** Continue videos from the last saved local position.
- **Clipboard detection:** Detect supported YouTube links at startup or continuously when background monitoring is enabled.
- **Browser integration:** Use the included Chromium-compatible extension to send supported YouTube links to HexPlayer through Native Messaging, export YouTube cookies with 1 click, or use the `hexplayer://` fallback protocol.
- **External tools management:** Check and update `yt-dlp`, Deno, and the YouTube.js/Innertube library from the app.
- **Universal Screen Reader Support:** Powered by [Prism](https://github.com/ethindp/prism), speech announcements automatically work with all active Windows screen readers (NVDA, JAWS, Narrator, System Access, etc.) and TTS engines.
- **Localization and themes:** Arabic and English interfaces, automatic language detection, and system, light, dark, and high contrast dark themes.

---

## Privacy

HexPlayer does not collect or transmit personal information to the developer. A cookies file is optional and is used locally by the app and its tools for YouTube features that require your signed-in session, such as YouTube account watch history, recommendations, likes, comments, chapters, and restricted content. Cookies can be imported automatically from an installed browser in Settings or selected manually. Without cookies, HexPlayer keeps played videos in local watch history on your computer.

Read the full [Privacy Policy](PRIVACY_POLICY.md) for details.

---

## Essential Keyboard Shortcuts

HexPlayer is designed to be fully navigable from the keyboard.

| Shortcut | Action |
| :--- | :--- |
| `Ctrl + F` | Search YouTube |
| `Ctrl + D` | Download from link or direct download |
| `Ctrl + Y` | Play YouTube link |
| `Ctrl + Shift + S` | Watch Shorts (requires cookies file) |
| `Ctrl + Shift + F` | Open Favorites |
| `Ctrl + H` | Open Watch History |
| `Ctrl + P` | Open download folder |
| `Alt + S` | Open settings |
| `F1` | Open user guide |
| `Enter` | Play selected list item as audio |
| `Ctrl + Enter` | Play selected list item as video |
| `Space` | Play or pause in the player |
| `Up / Down` (Shorts mode) | Cycle previous / next Short |
| `Shift + Up / Down` (Shorts mode) | Increase / decrease volume in Shorts mode |
| Arrow keys | Volume and seeking in the player |
| `Shift + , / .` | Change playback speed |
| `Ctrl + E` | Open equalizer in the player |
| `F12` | Choose audio output device in the player |

The full English and Arabic guides are available inside the app with `F1` and in:

- `src/docs/en/guide.txt`
- `src/docs/ar/guide.txt`

---

## Installation

### From GitHub Releases

1. Download the latest installer from the [Releases page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases).
2. Run `HexPlayer.exe`.
3. Follow the installer prompts. The installer can optionally download required external components.

### Using WinGet

Run the following command in Command Prompt or PowerShell:

```powershell
winget install HexPlayer
```

### Silent Installation

The installer supports command-line arguments for automated deployments:

- `/VERYSILENT`: fully silent installation.
- `/SILENT`: silent installation with a progress window.
- `/DOWNLOADCOMPONENTS=1`: force download of required external components such as `yt-dlp` and Deno during silent installation.
- `/DIR="C:\Path\To\Install"`: custom installation directory.

Examples:

```cmd
HexPlayer.exe /VERYSILENT /NORESTART /DOWNLOADCOMPONENTS=1
HexPlayer.exe /SILENT /NORESTART /DOWNLOADCOMPONENTS=1
```

---

## Browser Extension

HexPlayer includes a Chromium-compatible helper extension in `src/browser_extension`.

To use it:

1. Enable **Safe browser integration** in HexPlayer settings.
2. Open **External Tools > Open Browser Extension Folder** from HexPlayer.
3. Open your browser extensions page, such as `chrome://extensions`, `edge://extensions`, or `brave://extensions`.
4. Enable Developer mode.
5. Choose **Load unpacked** and select the folder opened by HexPlayer.

The extension can open supported YouTube links in HexPlayer from a context menu or toolbar button. Its options page includes diagnostics and a test link.

---

## Running From Source

1. Clone the repository:

   ```powershell
   git clone https://github.com/makhlwf/accessible_youtube_downloader_pro.git
   cd accessible_youtube_downloader_pro
   ```

2. Install UV if it is not already available:

   ```powershell
   winget install astral-sh.uv
   ```

3. Sync the locked project environment:

   ```powershell
   uv sync
   ```

4. Run the app:

   ```powershell
   uv run python src\accessible_youtube_downloader_pro.py
   ```

HexPlayer may prompt to download `yt-dlp` or Deno when a feature needs them and they are missing. The External Tools menu can also check for YouTube.js/Innertube updates and refresh its Deno cache when YouTube interaction features need repair.

To run the unit tests:

```powershell
uv run pytest tests/
```

---

## Building

To create a standalone build:

1. Sync the runtime and build dependencies:

   ```powershell
   uv sync --no-dev --group build
   ```

2. Run the build script:

   ```powershell
   uv run --no-dev --group build python scripts/build.py
   ```

3. Find the output in `dist/HexPlayer`.

---

## Project Structure

- `DEVELOPMENT.md`: detailed technical architecture, database schema, and developer guide.
- `CONTRIBUTING.md`: community guidelines, pull request instructions, and coding standards.
- `src/accessible_youtube_downloader_pro.py`: main application entry point.
- `src/media_player/`: MPV-backed media player and equalizer logic.
- `src/youtube_browser/`: search, playlist, and channel browsing logic.
- `src/gui/`: wxPython dialogs and windows.
- `src/download_handler/`: download handling through `yt-dlp`.
- `src/browser_extension/`: Chromium-compatible link helper extension.
- `src/docs/`: English and Arabic in-app user guides.
- `scripts/`: local maintenance and build utilities.
- `packaging/windows/`: Windows installer definition.
- `tests/`: unit tests for core helpers and dialogs.

---

## Contributing

We welcome contributions to HexPlayer! Please see our [Contributing Guide](CONTRIBUTING.md) for guidelines on reporting issues, setting up your environment, adhering to accessibility standards, and submitting pull requests.

For an in-depth technical overview of the application architecture, Deno RPC protocol, and media backends, refer to [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Acknowledgements

- **Original developer:** Suleiman Al Qusaimi.
- **Maintainer and fork author:** [Makhlwf](https://github.com/makhlwf).
- **Core tools:** [yt-dlp](https://github.com/yt-dlp/yt-dlp), [YouTube.js](https://ytjs.dev/), [wxPython](https://www.wxpython.org/), [MPV](https://mpv.io/), and [Deno](https://deno.com/).

---

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE) for details.

---

## Disclaimer

This project is a fork of the original Accessible YouTube Downloader Pro. It is provided as is, without warranty of any kind. Make sure your use complies with YouTube's Terms of Service and any applicable laws.
