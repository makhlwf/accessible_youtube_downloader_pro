# HexPlayer

![GitHub stars](https://img.shields.io/github/stars/makhlwf/accessible_youtube_downloader_pro)
![GitHub forks](https://img.shields.io/github/forks/makhlwf/accessible_youtube_downloader_pro)
![GitHub watchers](https://img.shields.io/github/watchers/makhlwf/accessible_youtube_downloader_pro)
![Release](https://img.shields.io/github/v/release/makhlwf/accessible_youtube_downloader_pro)
![Commits](https://img.shields.io/github/commit-activity/m/makhlwf/accessible_youtube_downloader_pro)

A Windows app for browsing, watching, and downloading YouTube content.

---

## Features
1. **Simple UI** – The app comes with a clean and simple user interface for easy navigation.  
2. **OS Compatibility** – Optimized for Windows to ensure smooth and fast operations.

---

## Downloading
Get the latest up-to-date version from the [releases page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases).

---

## Running from Source
1. Clone this repository locally:  
```bash
git clone https://github.com/makhlwf/accessible_youtube_downloader_pro.git

2. Make sure Python 3.11 is installed.


3. Install uv if you don’t have it:



pip install --upgrade uv

4. Change directory to the cloned repo.


5. Create a virtual environment (replace 3.14 with your Python version):



uv venv -p 3.14

6. Activate the virtual environment:



.venv\Scripts\activate

7. Install dependencies:



uv pip install -r requirements.txt

8. Change directory to source:



cd source

9. Run the app:



uv run accessible_youtube_downloader_pro.py


---

Building the App

If you want to create an executable:

1. Ensure you are in the root folder of the repo and the virtual environment is activated.


2. Install PyInstaller:



uv pip install --upgrade pyinstaller

3. Run the build script:



uv run build.py

4. The executable files will appear in the dist folder.




---

⚠️ Disclaimer

This project is a fork of the original Accessible YouTube Downloader Pro repository created by Sulaiman Al Qusaimi. I am not the original developer of this application.