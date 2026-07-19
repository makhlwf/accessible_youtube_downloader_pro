@echo off
REM quick build + package script

call .venv\Scripts\activate.bat || exit /b

uv run build.py || exit /b

REM build installer
iscc inno.iss
