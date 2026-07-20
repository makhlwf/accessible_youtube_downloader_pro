@echo off
REM quick build + package script

call .venv\Scripts\activate.bat || exit /b

uv run scripts\build.py || exit /b

REM build installer
iscc packaging\windows\inno.iss
