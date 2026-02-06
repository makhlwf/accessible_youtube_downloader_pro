@echo off
REM quick run script for fast development

call .venv\Scripts\activate.bat || exit /b
cd /d "%~dp0source" || exit /b
uv run accessible_youtube_downloader_pro.py
