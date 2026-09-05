---
name: desktop-screen-reader-testing
description: >-
  Use when testing desktop accessibility with NVDA Speech Viewer,
  JAWS, Windows Narrator, Accessibility Insights, or evaluating screen reader speech announcements.
---

# Desktop Screen Reader Testing & Speech Verification

## Overview

Screen reader users interact with desktop software entirely through keyboard navigation and synthesized speech or braille displays. Automated unit tests catch structural bugs, but verifying the actual user experience requires testing with real assistive technology (NVDA, JAWS, Narrator) and utilizing inspection tools such as **NVDA Speech Viewer**.

## When to Use

- Testing how NVDA, JAWS, or Windows Narrator announces dialogs, controls, and playback states.
- Verifying speech announcements without audio hardware via NVDA's text-based Speech Viewer.
- Diagnosing double-speech announcements or silent controls.
- Evaluating keyboard shortcut ergonomics (Enter, Escape, Space, Arrow keys, Alt mnemonics).
- Formulating manual accessibility acceptance test plans for desktop releases.

**When NOT to use:**
- Automated headless CI testing (use `pytest-mocking-strategy`).

## Core Patterns & Invariants

### 1. NVDA Speech Viewer Verification Pattern
Developers and agents can verify exact screen reader speech output as text without listening to audio:
1. Start NVDA: `Ctrl + Alt + N` (or launch `nvda.exe`).
2. Open NVDA Menu (`NVDA + N` or `Insert + N`).
3. Select **Tools** -> **Speech Viewer**.
4. A floating text window displays every word spoken by NVDA in real time.
5. Perform actions in HexPlayer and observe the exact transcript.

```
[Speech Viewer Transcript Example]
HexPlayer - Accessible YouTube Downloader Pro  window
Search Videos...  edit text  blank
Entered search: Flutter Accessibility
Playback started: Flutter Accessibility Tutorial by CodeLabs
```

### 2. The Keyboard-Only Interaction Protocol
Before testing with speech output, verify keyboard operability:
- Disconnect or ignore the mouse.
- Can every feature be reached using `Tab`, `Shift+Tab`, and Arrow keys?
- Does `Enter` activate default actions in dialogs?
- Does `Escape` close dialogs and modals without hanging the process?
- Is there any focus trap where focus cannot escape a container?

### 3. Speech Priority & Interruption Rules
In HexPlayer, speech announcements are dispatched via `speech_client.speak(message, interrupt=True)`:
- State transitions (Play, Pause, Stop, Seek, Chapter change) must use `interrupt=True` to immediately inform the user.
- Status announcements (Download progress percentages) should be throttled or use `interrupt=False` so they do not drown out user navigation speech.

## Quick Reference

| Tool / Action | Command / Shortcut | Purpose |
| :--- | :--- | :--- |
| **Start / Stop NVDA** | `Ctrl + Alt + N` | Windows open-source screen reader |
| **NVDA Modifier Key** | `Insert` or `Caps Lock` | Primary screen reader command key |
| **Read Current Focus**| `NVDA + Tab` | Announces currently focused control |
| **Speech Viewer** | NVDA Menu -> Tools -> Speech Viewer | View spoken speech as real-time text |
| **Start Narrator** | `Win + Ctrl + Enter` | Built-in Windows screen reader |
| **JAWS Focus Read** | `Insert + Tab` | Commercial Windows screen reader |

## Implementation Procedures

### Step 1: Performing a Manual Dialog Audit
1. Launch HexPlayer.
2. Open target dialog (e.g. Search Dialog via `Ctrl+F`).
3. Check initial focus: Screen reader must immediately announce dialog title and the first control.
4. Tab through all controls in sequence:
   - Check that control name matches visible label.
   - Check that control role (Edit, Button, Choice) is verbalized.
5. Press `Escape`: Verify dialog dismisses and focus returns to main window.

### Step 2: Verifying Playback Announcements
1. Play a YouTube track.
2. Press `Space`: Verify speech announces "Paused" or "Playing".
3. Press `Right Arrow`: Verify seek delta or position is vocalized.
4. Jump chapter with `[` or `]`: Verify new chapter title is vocalized.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Testing only with mouse clicks | Blind users never click mouse coordinates | Test 100% with keyboard shortcuts |
| Testing only with eyes | Cannot detect missing accessible labels | Use NVDA Speech Viewer transcript |
| Announcing non-stop speech | Saturates TTS queue, blocks user navigation | Speak only on discrete state events |
| Leaving focus orphaned on close | Focus jumps to desktop taskbar or resets to top | Explicitly call `calling_control.SetFocus()` |

## Verification & Quality Gates

- **Visual / Speech Transcript**: Open NVDA Speech Viewer and verify that dialog navigation produces clean text without "unknown" controls.
- **Keyboard Ergonomics**: All actions accessible via keyboard without mouse assistance.
- **Narrator Smoke Test**: Run Windows Narrator (`Win + Ctrl + Enter`) to confirm standard UIA compatibility.
