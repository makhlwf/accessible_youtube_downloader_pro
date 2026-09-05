# GitHub Copilot Instructions for HexPlayer (Accessible YouTube Downloader Pro)

HexPlayer is an accessible Windows desktop application for blind and visually impaired users.

## Core Directives for Code Generation:
- **GUI & Threading**: All UI manipulations from worker threads must be marshaled using `wx.CallAfter(callable, *args)`.
- **Accessibility**: Provide accessible control names, ensure `wx.TAB_TRAVERSAL` style on composite panels, and announce playback/state transitions via `from speech_client import speech_client; speech_client.speak(msg, interrupt=True)`.
- **Localization**: Use `from language_handler import _` and `_("...")` for all user-facing strings with named placeholders.
- **Reference Skills**: Procedural runbooks and invariants reside in `.agents/skills/`.
- **Verification**: Ensure code passes `uv run python scripts/agent_preflight.py`.
