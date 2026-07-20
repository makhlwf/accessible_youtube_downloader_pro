@echo off
REM quick run script for fast development

cd /d "%~dp0" || exit /b
uv run python src\accessible_youtube_downloader_pro.py
