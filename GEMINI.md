# HexPlayer Guidelines for Gemini & Antigravity

Welcome to **HexPlayer (Accessible YouTube Downloader Pro)**.

Please review and adhere to the project invariants, architectural subsystems, and commandments defined in [AGENTS.md](./AGENTS.md).

## Key Directives:
1. **Thread Safety**: All GUI updates from background threads must use `wx.CallAfter(callable, *args)`.
2. **Screen Reader First**: Every interactive control must have an accessible label, `wx.TAB_TRAVERSAL`, and announce state via `speech_client.speak(msg)`.
3. **i18n Freshness**: Wrap all user text in `_()`. Update `messages.pot` with `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`.
4. **Skills Location**: Consult the 17 domain skills in `.agents/skills/` and team workflows in `.agents/ORCHESTRATION.md`.
5. **Preflight Verification**: Always execute `uv run python scripts/agent_preflight.py` before concluding any task.
