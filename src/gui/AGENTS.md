# GUI & Accessibility Directory Rules (`src/gui/`)

This directory contains the user interface dialogs and accessible controls for HexPlayer.
When modifying or creating files in this directory, follow these rules strictly:

1. **`wx.CallAfter` is Mandatory**:
   Any callback from background threads (search results, download progress, player state) MUST be dispatched to the GUI thread via `wx.CallAfter(callable, *args)`.

2. **Keyboard Traversal & Focus Management**:
   - Every custom panel or composite container MUST include the style `wx.TAB_TRAVERSAL`.
   - Never remove or trap keyboard focus.
   - When a modal dialog opens, remember the caller's focused control. When the dialog closes, restore focus to the calling element so screen reader users are not disoriented.
   - Bind `wx.EVT_CHAR_HOOK` or `wx.EVT_KEY_DOWN` to handle Escape (`wx.ID_CANCEL` / close) and Enter (`wx.ID_OK`).

3. **Screen Reader Announcements**:
   - Provide immediate auditory confirmation for important actions using:
     ```python
     from speech_client import speech_client

     speech_client.speak(_("Operation completed."), interrupt=True)
     ```
   - Do not spam `speak()` on continuous events (such as slider drags). Throttle or announce only on release.

4. **Theme & Dark Mode Support**:
   - Use `theme_handler.py` utilities instead of hardcoding RGB colours.
   - Respect Windows high-contrast modes and `MSWEnableDarkMode`.

5. **Translatable Text**:
   - Wrap all labels, button texts, error messages, and dialog titles in `_()`.
