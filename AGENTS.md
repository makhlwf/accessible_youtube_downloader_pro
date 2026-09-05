# HexPlayer (Accessible YouTube Downloader Pro) - Agent Guidelines & Invariants

Welcome, coding agent. This repository is **HexPlayer (Accessible YouTube Downloader Pro)**, a specialized Windows desktop YouTube client engineered specifically for **blind and visually impaired users**.

Every line of code you write must prioritize screen reader responsiveness, keyboard navigability, thread safety, and localization integrity.

---

## 1. Five Non-Negotiable Commandments

1. **`wx.CallAfter` for Thread Safety**:
   - The wxPython GUI main thread must NEVER be accessed directly from background threads, worker threads, async tasks, or MPV/yt-dlp callbacks.
   - Always route GUI updates through `wx.CallAfter(callable, *args)` or custom wx events.

2. **Screen Reader Accessibility (a11y) First**:
   - Blind users navigate entirely by keyboard and auditory feedback.
   - Every interactive control must have an accessible label, tab traversal (`wx.TAB_TRAVERSAL`), and standard keyboard shortcuts (Enter, Space, Escape).
   - Announce state transitions, playback events, and errors immediately via `from speech_client import speech_client; speech_client.speak(msg, interrupt=True)`.

3. **Internationalization (i18n) Discipline**:
   - Never hardcode user-facing English strings in dialogs or messages.
   - Always import gettext translation wrapper: `from language_handler import _`.
   - Never concatenate translatable strings. Use named placeholders: `_("Downloaded {title}").format(title=video_title)`.
   - If you add or modify any user-facing string, update the template via:
     `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`

4. **Path Safety & Portability**:
   - Never hardcode `%APPDATA%`, absolute paths, or assume the current working directory.
   - Always resolve paths via `paths.py` (`paths.settings_path()`, `paths.get_app_path()`).
   - Respect portable mode when `portable.dat` or portable markers exist.

5. **Mandatory Preflight Verification**:
   - Before claiming any task is complete or reporting success, you must run:
     `uv run python scripts/agent_preflight.py`
   - This executes:
     1. `scripts/verify_skills.py` (Validates all 17 skills against agentskills.io format)
     2. `uv run ruff check .` (Linter)
     3. `uv run python scripts/check_translations.py` (Translation catalog check)
     4. `uv run pytest tests/` (Unit & integration test suite)

---

## 2. System Architecture & Subsystem Ownership

| Subsystem | Key Files | Responsible Skill | Owning Agent |
| :--- | :--- | :--- | :--- |
| **Accessible GUI** | `src/gui/*.py`, `src/accessible_youtube_downloader_pro.py` | `wx-accessible-gui`, `wxpython-architecture` | `AccessibilityUIAgent` |
| **Desktop A11y & Testing** | `src/gui/custom_controls.py`, `src/speech_client.py` | `desktop-a11y-specialist`, `desktop-screen-reader-testing` | `DesktopA11ySpecialist` |
| **Media Playback** | `src/media_player/*.py`, `src/libmpv-2.dll` | `mpv-media-engine` | `MediaPlaybackAgent` |
| **SponsorBlock** | `src/sponsorblock_handler.py` | `sponsorblock-engine` | `SponsorBlockSpecialist` |
| **Media Downloader** | `src/download_handler/*.py`, `yt-dlp` | `ytdlp-downloader-engine` | `DownloaderAndYtdlpAgent` |
| **Deno / InnerTube** | `src/service.js`, `src/deno_service.py` | `innertube-rpc-bridge` | `InnerTubeAndDenoAgent` |
| **PO Token & Anti-Bot** | `src/pot_provider_service.py` | `youtube-pot-security` | `PoTokenSecurityAgent` |
| **Browser Cookie Auth** | `src/cookies_manager.py` | `youtube-cookies-auth` | `AuthCookiesSpecialist` |
| **Clipboard Monitor** | `src/gui/auto_detect_dialog.py` | `clipboard-url-monitor` | `AccessibilityUIAgent` |
| **Database & Settings**| `src/database.py`, `src/settings_handler.py` | `sqlite-state-storage` | `StorageAndStateAgent` |
| **Browser Extension** | `src/browser_extension/*`, `src/native_messaging_host.py` | `chrome-native-messaging`| `IntegrationAndPackagingAgent` |
| **Packaging & Build** | `scripts/build.py`, `packaging/windows/inno.iss` | `windows-build-packaging`| `IntegrationAndPackagingAgent` |
| **GitHub Releases** | `scripts/`, `dist/` | `github-release-operations` | `GitHubReleaseManager` |
| **Testing & Quality** | `tests/*.py`, `tests/conftest.py` | `pytest-mocking-strategy` | `QualityAndVerificationAgent` |
| **Translations** | `messages.pot`, `src/languages/` | `gettext-i18n-pipeline` | `QualityAndVerificationAgent` |

---

## 3. Skill & Agent Orchestration

Detailed procedures, edge-case playbooks, and runbooks are available in `.agents/skills/`.
When working on any area of the codebase, consult the corresponding skill:
- Review `.agents/skills/<skill-name>/SKILL.md` before making modifications.
- Reference `.agents/ORCHESTRATION.md` for agent collaboration protocols.
