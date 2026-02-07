@echo off
REM quick build + package script

call .venv\Scripts\activate.bat || exit /b

uv run build.py || exit /b

REM move build artifacts up one level
move "dist\HexPlayer\_internal" "dist\" || exit /b
move "dist\HexPlayer\HexPlayer.exe" "dist\" || exit /b

REM remove empty HexPlayer folder
rmdir "dist\HexPlayer"

REM build installer
iscc inno.iss
