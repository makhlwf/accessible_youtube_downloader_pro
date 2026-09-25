"""Headless command-line interface for HexPlayer.

This package exposes the application's features (search, media info, download,
subtitles, comments, chapters, likes, channels, playlists, home/shorts feeds,
favorites/history, settings and dependency management) without starting the
wxPython GUI. It reuses the same backend modules the desktop app uses.

The entry point is :func:`main`, invoked by ``src/hexplayer_cli.py`` (the
frozen ``hexplayer`` console executable) and by ``python -m cli``.
"""

from cli.app import main

__all__ = ["main"]
