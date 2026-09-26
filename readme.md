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
  <b>HexPlayer</b> is an accessible Windows and Linux application for searching, browsing, watching, and downloading YouTube content with a keyboard-first interface.
</p>

---

## Overview

HexPlayer is the current continuation of Accessible YouTube Downloader Pro. It is designed for blind and visually impaired Windows and Linux users who want a screen-reader friendly way to use YouTube without relying on the YouTube web interface. On Windows, HexPlayer works with screen readers (NVDA, JAWS, Narrator, System Access, etc.) and Windows speech engines via [Prism](https://github.com/ethindp/prism).

The current application version is **5.3.0**.

### Supported systems

- **Windows:** Intended for modern 64-bit Windows systems, especially Windows 10 and Windows 11. Older Windows releases and 32-bit systems may not work reliably with the current Python runtime and external tools.
- **Linux:** Native support for **Fedora 43+ (x86_64)** via RPM packages and **Ubuntu 24.04+ (amd64)** via DEB packages, with glibc 2.39 or newer, in a graphical desktop session. Both distributions are fully natively supported and verified in automated CI and container smoke tests. Portable tarballs are also provided for other compatible x86_64 Linux distributions.
- **Other platforms:** No macOS packages are provided, and no ARM release support is promised.

Linux speech announcements use Prism with Speech Dispatcher. Orca is the screen reader for desktop navigation; install and enable it separately if needed. Automated checks do not establish screen-reader usability: focus, labels, keyboard navigation, and announcements still require manual Orca validation in a real Linux desktop session.

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
- **Screen reader support:** Powered by [Prism](https://github.com/ethindp/prism), with Windows screen reader/TTS support and Linux Speech Dispatcher announcements. Linux Orca usability still needs manual desktop validation.
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

## Command Line Interface

HexPlayer includes a dedicated command line tool, `hexplayer`, that exposes the
application's YouTube features without opening the graphical interface. It
supports every feature except playback, works in both human-readable and
`--json` output modes, and is designed to be usable in a terminal with a screen
reader.

On Windows, the installer offers an optional task to add HexPlayer to your
per-user `PATH` so the `hexplayer` command is available from any terminal. On
Linux, the native packages already install a `hexplayer` launcher on `PATH`.

```bash
hexplayer search "lofi hip hop"
hexplayer download https://youtu.be/VIDEO_ID --format mp3
hexplayer --json info https://youtu.be/VIDEO_ID
```

See the full [Command Line Interface guide](cli.md) for every command and
option, or run `hexplayer --help`.

Building HexPlayer into your own application? The
[Developer API guide](api.md) documents the `--json` contract, the expected
output of every command, integration examples (Python, Node.js, shell), and the
attribution HexPlayer requires under its GPL-3.0 license.

---

## Installation

### Windows: From GitHub Releases

1. Download the latest installer from the [Releases page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases).
2. Run `HexPlayer.exe`.
3. Follow the installer prompts. The installer can optionally download required external components.

### Windows: Using WinGet

Run the following command in Command Prompt or PowerShell:

```powershell
winget install HexPlayer
```

### Windows: Silent Installation

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

## Linux Installation

Open the [Releases page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases), choose a stable release or the **beta** pre-release, and expand its **Assets** list. Beta builds are for testing and can change independently of stable releases. Choose a release that lists the Linux asset you need; if your chosen release does not include it, select another release with that asset or use [the source setup](#running-from-source). Do not use the Windows installer on Linux.

HexPlayer provides native packages for **Fedora / RHEL** (`.rpm`), **Ubuntu / Debian** (`.deb`), and generic `.tar.xz` archives for x86_64 distributions with glibc 2.39 or newer. Each asset is accompanied by a `.sha256` checksum file. In all commands below, replace `VERSION` with the version in the downloaded filename (e.g. `4.8.0`).

### Quick Start: Unified Linux Installer (`install.sh`)

HexPlayer includes an automated installer script that detects your distribution, installs required packages or sets up from source, and registers the URL scheme and browser extension integration:

```bash
# Auto-detect distribution and install prebuilt package (.rpm or .deb) found in current directory
bash packaging/linux/install.sh

# Or install a specific downloaded package:
bash packaging/linux/install.sh --package ./HexPlayer-VERSION-1.x86_64.rpm

# Verify screen reader (Orca), AT-SPI2, and Speech Dispatcher readiness:
bash packaging/linux/install.sh --check-accessibility
```

### Native RPM Package: Fedora, RHEL, CentOS, Rocky, AlmaLinux

Download the `HexPlayer-VERSION-1.x86_64.rpm` asset and its matching `.sha256` file from the release. Run the checksum verification in the download directory and install via DNF:

```bash
sha256sum -c HexPlayer-VERSION-1.x86_64.rpm.sha256
sudo dnf install ./HexPlayer-VERSION-1.x86_64.rpm
hexplayer
```

DNF automatically resolves and installs all required system dependencies (GTK 3, libmpv, FFmpeg, Speech Dispatcher, Secret Storage, WebKitGTK). Start HexPlayer from your application menu or with `hexplayer` as your normal desktop user, never with `sudo`.

### Native Debian Package: Ubuntu 24.04+, Debian 12+, Linux Mint, Pop!_OS

Download the `HexPlayer-VERSION-linux-amd64.deb` asset and its matching `.sha256` file from the same release:

```bash
sha256sum -c HexPlayer-VERSION-linux-amd64.deb.sha256
sudo apt install ./HexPlayer-VERSION-linux-amd64.deb
hexplayer
```

APT installs the package and its declared runtime dependencies. Start HexPlayer from your application menu or with `hexplayer` as your normal desktop user, never with `sudo`.

### Tarball: Generic x86_64 Linux Distributions

Download the `linux-x86_64.tar.xz` asset and its matching `.sha256` file from the same release. The tarball is not a dependency-free portable build. Install your distribution's runtime packages first, then extract and run.

#### Fedora runtime packages

```bash
sudo dnf install gtk3 mpv-libs ffmpeg-free libnotify libsecret webkit2gtk4.1 mesa-libGL mesa-libGLU libSM libXtst speech-dispatcher speech-dispatcher-espeak-ng xdg-utils xclip wl-clipboard
```

Fedora is fully natively supported and verified in CI using native RPM and container validation tests. Note that Fedora's default `ffmpeg-free` package provides basic codecs; if your workflow requires proprietary codecs (such as certain H.264/AAC media), consider enabling RPM Fusion multimedia packages.

#### Ubuntu 24.04 runtime packages

```bash
sudo apt update
sudo apt install libc6 libstdc++6 libgtk-3-0t64 libmpv2 ffmpeg libnotify4 libsecret-1-0 libwebkit2gtk-4.1-0 libgl1 libglu1-mesa libsm6 libxtst6 libspeechd2 speech-dispatcher xdg-utils
sudo apt install espeak-ng xclip wl-clipboard
```

#### Other Linux distributions

Use your distribution's package manager to install equivalents of the runtime libraries above, including GTK 3, WebKitGTK 4.1 (GTK 3/libsoup 3), libmpv, FFmpeg/ffprobe, libnotify, libsecret, OpenGL/GLU, X11 SM/XTest, and Speech Dispatcher with a speech engine. Install desktop and clipboard helpers appropriate to your session. A musl-based distribution or a system with glibc older than 2.39 is not a target for this tarball.

#### Verify, extract, and launch

```bash
sha256sum -c HexPlayer-VERSION-linux-x86_64.tar.xz.sha256
```

Continue only if verification succeeds:

```bash
tar -xf HexPlayer-VERSION-linux-x86_64.tar.xz
./HexPlayer/HexPlayer
```

Extract into a user-writable directory and launch in your graphical desktop session without `sudo`; system FFmpeg and libmpv remain required.

### Linux troubleshooting

- **Missing shared library:** Launch from a terminal and note the exact missing `.so` name. Search your distribution's package providers, for example `dnf provides '*/libNAME.so.N'` on Fedora, replacing the placeholder with the reported filename. On Ubuntu, use `apt-file search libNAME.so.N` after installing `apt-file` and updating its index. Install a matching package from your distribution's repositories; do not copy libraries from Ubuntu or create symlinks between incompatible SONAME versions.
- **`GLIBC_2.39 not found` or another ABI/version error:** Use a compatible distribution release or build from source against your system libraries. Do not manually replace the system glibc. Newer glibc alone does not resolve other bundled/system library mismatches.
- **No speech or desktop navigation feedback:** Check Speech Dispatcher and its speech engine in your logged-in desktop session. Install and enable Orca separately for navigation. Automated tests do not verify audible speech or Orca interaction.
- **Playback or conversion fails:** Confirm system `ffmpeg`, `ffprobe`, and libmpv are installed and support the requested codecs. On Fedora, account for `ffmpeg-free` codec limitations.

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

On Linux, safe browser integration registers a per-user desktop handler for `hexplayer://` and Native Messaging manifests for standard Chrome, Chromium, Edge, and Brave configuration paths. Sandboxed Snap/Flatpak browsers and custom profile paths may need additional setup and are not covered by automatic registration. See the [browser extension instructions](src/browser_extension/README.md) for paths and troubleshooting.

---

## Running From Source

### Windows

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

### Linux: Native Fedora & Ubuntu source setup

Install Git and curl if needed (`sudo dnf install git curl` on Fedora or `sudo apt install git curl` on Ubuntu). Install uv using the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/); reopen your terminal if required so `uv` is on PATH.

```bash
git clone https://github.com/makhlwf/accessible_youtube_downloader_pro.git
cd accessible_youtube_downloader_pro
sudo bash packaging/linux/install-deps.sh
uv python install 3.14.7
UV_CONCURRENT_BUILDS=1 uv sync --locked
uv run python src/accessible_youtube_downloader_pro.py
```

`packaging/linux/install-deps.sh` automatically detects your distribution (Fedora/RHEL or Ubuntu/Debian) and installs the required build and runtime dependencies using DNF or APT. Python 3.14.7 is pinned in `.python-version`; wxPython may build from source, so synchronization can take time and memory. Run uv and HexPlayer as your normal user, not with `sudo`.

### First launch and user data

An Internet connection is needed for missing runtime downloads on first launch or when a feature first needs them, including `yt-dlp`, Deno, and YouTube.js dependencies. On Linux, managed Deno is installed per-user under `$XDG_DATA_HOME/HexPlayer/js_runtime` (default `~/.local/share/HexPlayer/js_runtime`); FFmpeg and libmpv come from system packages, not Windows binaries. The External Tools menu can check for updates and refresh the Deno cache.

Linux settings, database, logs, downloaded tools, and the refreshed browser extension normally live in `$XDG_DATA_HOME/HexPlayer` (default `~/.local/share/HexPlayer`). Browser manifests and autostart entries use `$XDG_CONFIG_HOME` (default `~/.config`); the protocol desktop entry uses `$XDG_DATA_HOME/applications`. A `portable.dat` marker switches app data to the application's `data` directory. Downloads default to `HexPlayer` inside the XDG Downloads directory, or `~/Downloads` if none is configured.

### Tests and CI coverage

For fast unit tests without compiling native wxPython, use the same setup as the Windows and Ubuntu 24.04 unit CI jobs:

```bash
uv sync --locked --no-install-package wxpython
uv run --no-sync pytest tests/ -v -o faulthandler_timeout=60
```

These are mocked unit and platform import tests, not native GUI validation. The Ubuntu 24.04 native job installs dependencies, runs a full `uv sync --locked` with serialized builds and a native dependency cache, then runs `packaging/linux/runtime_smoke.py --packaging-smoke-test` under D-Bus and Xvfb. The smoke script opens and closes a real wx/GTK frame, imports Prism and Linux dependencies, and checks generated offline audio playback through system libmpv to end-of-file with null audio/video outputs. It does not test YouTube streaming, audible output, Prism/Speech Dispatcher announcements, or Orca usability.

The release build workflow additionally checks package metadata and SHA-256 checksums, installs the `.deb` through APT, runs a dedicated Fedora container job (`fedora-smoke`) validating native `.rpm` installation, Speech Dispatcher and AT-SPI2 availability, validates desktop files, and exercises frozen startup and native-host message framing as a normal user for both installed packages and tarball archives. Lint/format CI runs Ruff on Windows and Ubuntu. Screen-reader behavior and keyboard navigation still need manual testing in a real desktop session.

To run the full repository preflight (skills, Ruff lint, translation catalogs, and tests):

```bash
uv run python scripts/agent_preflight.py
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
