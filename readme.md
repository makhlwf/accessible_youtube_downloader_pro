# 🎥 HexPlayer (Accessible YouTube Downloader Pro)

[![GitHub release](https://img.shields.io/github/v/release/makhlwf/accessible_youtube_downloader_pro?style=for-the-badge&color=blue)](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases)
[![Python Version](https://img.shields.io/badge/Python-3.11+-brightgreen?style=for-the-badge&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows)](https://www.microsoft.com/windows)
[![Accessibility](https://img.shields.io/badge/Accessibility-Screen%20Reader%20Friendly-orange?style=for-the-badge)](https://en.wikipedia.org/wiki/Web_Accessibility)

**HexPlayer** is a powerful, lightweight, and highly accessible Windows application designed for browsing, watching, and downloading YouTube content. Built with a focus on blind and visually impaired users, it provides a seamless experience without the complexities of a web browser.

---

## ✨ Key Features

- 🔍 **Direct Search:** Search for videos, playlists, and live streams directly within the app.
- 🎧 **Dedicated Media Player:** An accessible built-in player that supports audio and video modes.
- 📥 **Advanced Downloading:** Download content in various formats (MP4, MP3, M4A) with `yt-dlp` integration.
- 🔗 **Smart Clipboard Detection:** Automatically detects YouTube links from your clipboard on startup.
- 📁 **Auto-Organization:** Automatically creates folders for playlists and channels during downloads.
- ⚡ **Background Tasks:** Watch your favorite videos while downloading others in the background.
- 🌍 **Multilingual:** Full support for **Arabic** and **English** with automatic system language detection.
- 🚀 **Performance:** Optimized for Windows 10/11 (64-bit).

---

## ⌨️ Essential Keyboard Shortcuts

HexPlayer is designed to be fully navigable via keyboard.

| Shortcut | Action |
| :--- | :--- |
| **`Ctrl + F`** | Search YouTube |
| **`Ctrl + D`** | Download from Link / Direct Download |
| **`Ctrl + Y`** | Play YouTube Link |
| **`Ctrl + Shift + F`** | Open Favorites |
| **`Ctrl + P`** | Open Download Folder |
| **`Alt + S`** | Open Settings |
| **`F1`** | User Guide |
| **`Space`** | Play / Pause (Player) |
| **`Arrows`** | Volume and Seeking (Player) |

---

## 🚀 Getting Started

### Installation
1. Download the latest version from the [Releases Page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases).
2. Run the `HexPlayer.exe` installer.
3. Follow the on-screen instructions (it will optionally download `yt-dlp` for you).

### Running from Source (For Developers)
1. **Clone the repo:**
   ```bash
   git clone https://github.com/makhlwf/accessible_youtube_downloader_pro.git
   cd accessible_youtube_downloader_pro
   ```
2. **Setup Virtual Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the App:**
   ```bash
   cd source
   python accessible_youtube_downloader_pro.py
   ```

---

## 🛠️ Building the Executable
To create your own standalone executable:
1. Ensure you are in the root directory and your venv is active.
2. Install PyInstaller: `pip install pyinstaller`
3. Run the build script: `python build.py`
4. Find your app in the `dist/HexPlayer` folder.

---

## 🤝 Acknowledgements
- **Original Developer:** Suleiman Al Qusaimi.
- **Maintainer & Fork Author:** [Makhlwf](https://github.com/makhlwf).
- **Core Engine:** Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [wxPython](https://www.wxpython.org/).

---

## ⚠️ Disclaimer
This project is a fork of the original "Accessible YouTube Downloader Pro". It is provided "as is" without warranty of any kind. Please ensure you comply with YouTube's Terms of Service when using this application.

---
<p align="center">Made with ❤️ for the accessibility community.</p>
