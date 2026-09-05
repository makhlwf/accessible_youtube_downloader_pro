# HexPlayer (Accessible YouTube Downloader Pro) - Claude Guidelines

Welcome to **HexPlayer (Accessible YouTube Downloader Pro)**. This Windows desktop YouTube client is engineered specifically for **blind and visually impaired users**.

Every action, line of code, and commit must strictly prioritize screen reader responsiveness, keyboard navigability, thread safety, and localization integrity.

---

## 1. Five Non-Negotiable Invariants

1. **`wx.CallAfter` for Thread Safety**:
   - Never access the wxPython GUI main thread from background threads, worker threads, async tasks, or MPV/yt-dlp callbacks.
   - Always route GUI updates through `wx.CallAfter(callable, *args)` or custom wx events.

2. **Screen Reader Accessibility (a11y) First**:
   - Blind users navigate entirely by keyboard and auditory feedback.
   - Every interactive control must have an accessible label, tab traversal (`wx.TAB_TRAVERSAL`), and standard keyboard shortcuts (Enter, Space, Escape).
   - Announce state transitions, playback events, and errors immediately via:
     `from speech_client import speech_client; speech_client.speak(msg, interrupt=True)`

3. **Internationalization (i18n) Discipline**:
   - Never hardcode user-facing English strings. Always use `from language_handler import _`.
   - Never concatenate translatable strings. Use named placeholders: `_("Downloaded {title}").format(title=video_title)`.
   - If you modify user-facing text, update the template via:
     `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`

4. **Path Safety & Portability**:
   - Never hardcode `%APPDATA%`, absolute paths, or assume CWD.
   - Always resolve paths via `paths.py` (`paths.settings_path()`, `paths.get_app_path()`).
   - Respect portable mode when `portable.dat` or portable markers exist.

5. **Mandatory Preflight Verification**:
   - Before completing any task or claiming success, always run:
     `uv run python scripts/agent_preflight.py`

---

## 2. Specialized Skills & Runbooks (`.agents/skills/`)

Consult the appropriate skill in `.agents/skills/` before making changes to any subsystem:
- **Accessible GUI**: `.agents/skills/wx-accessible-gui/SKILL.md`
- **wx Layout & Events**: `.agents/skills/wxpython-architecture/SKILL.md`
- **Desktop A11y (UIA/MSAA)**: `.agents/skills/desktop-a11y-specialist/SKILL.md`
- **Screen Reader Testing**: `.agents/skills/desktop-screen-reader-testing/SKILL.md`
- **Media Engine (MPV)**: `.agents/skills/mpv-media-engine/SKILL.md`
- **SponsorBlock**: `.agents/skills/sponsorblock-engine/SKILL.md`
- **Media Downloader**: `.agents/skills/ytdlp-downloader-engine/SKILL.md`
- **Deno / InnerTube**: `.agents/skills/innertube-rpc-bridge/SKILL.md`
- **PO Token & Anti-Bot**: `.agents/skills/youtube-pot-security/SKILL.md`
- **Cookie Authentication**: `.agents/skills/youtube-cookies-auth/SKILL.md`
- **Clipboard Monitor**: `.agents/skills/clipboard-url-monitor/SKILL.md`
- **Browser Extension**: `.agents/skills/chrome-native-messaging/SKILL.md`
- **Database & Settings**: `.agents/skills/sqlite-state-storage/SKILL.md`
- **Packaging & Build**: `.agents/skills/windows-build-packaging/SKILL.md`
- **GitHub Releases**: `.agents/skills/github-release-operations/SKILL.md`
- **Testing & Quality**: `.agents/skills/pytest-mocking-strategy/SKILL.md`
- **Translations**: `.agents/skills/gettext-i18n-pipeline/SKILL.md`

Full multi-agent team coordination guidelines are available in `.agents/ORCHESTRATION.md`.
