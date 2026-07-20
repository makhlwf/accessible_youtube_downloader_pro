@echo off
REM quick build + package script

cd /d "%~dp0" || exit /b

uv run --no-dev --group build python scripts\build.py || exit /b

REM build installer
iscc packaging\windows\inno.iss
