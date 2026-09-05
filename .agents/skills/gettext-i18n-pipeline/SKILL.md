---
name: gettext-i18n-pipeline
description: >-
  Use when adding or modifying user-facing text, updating translation catalogs,
  running Babel extraction, compiling .mo files, or handling Arabic RTL UI rendering.
---

# Internationalization (i18n) & Arabic RTL Pipeline

## Overview

HexPlayer is fully localized in English (`en`) and Arabic (`ar`) via GNU gettext and Babel. Because HexPlayer has a large Arabic-speaking visually impaired user base, preserving string extraction freshness and ensuring correct Right-to-Left (RTL) layout rendering on Windows is a critical quality standard.

## When to Use

- Adding, editing, or removing any user-visible strings in dialogs, menus, tooltips, or speech announcements.
- Updating translation template `messages.pot` or language `.po`/`.mo` files in `src/languages/`.
- Resolving CI failures from `scripts/check_translations.py`.
- Debugging Arabic text truncation, bidirectional (BiDi) numbers, or RTL layout issues in wxPython.

**When NOT to use:**
- Modifying internal variable names, log statements, or private JSON keys.

## Core Patterns & Invariants

### 1. Mandatory String Tagging with `_()`
Import the gettext translation wrapper and tag all user-visible text:

```python
# ✅ REQUIRED: Tag with _()
from language_handler import _

status_label = wx.StaticText(self, wx.ID_ANY, _("Download complete"))
```

### 2. Never Concatenate Translatable Strings
Word order varies significantly between English and Arabic (SVO vs VSO). Always use named string formatting placeholders:

```python
# ❌ PROHIBITED: String concatenation breaks translation
message = _("Downloaded ") + str(count) + _(" files.")

# ✅ REQUIRED: Named formatting placeholder
message = _("Downloaded {count} files.").format(count=count)
```

### 3. Translation Catalog Freshness Gate
HexPlayer enforces that `messages.pot` matches the codebase exactly in CI. Whenever strings change in `src/`, extract new strings immediately:

```powershell
uv run pybabel extract -F babel.cfg -k _ -o messages.pot .
```

Verify with:
```powershell
uv run python scripts/check_translations.py
```

### 4. Arabic RTL wxPython Considerations
In Arabic mode, wxPython mirrors dialog controls horizontally. When constructing compound labels with timestamps or file extensions (e.g. `song.mp3 - [03:45]`), wrap the formatted variables properly to prevent Windows BiDi engines from flipping punctuation marks:

```python
# Use Unicode directional markers if necessary for BiDi stability
def format_bidi_safe(title: str, duration: str) -> str:
    return f"{title} \u200e({duration})\u200e"
```

## Quick Reference

| Command | Purpose |
| :--- | :--- |
| `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .` | Extract translatable strings into template |
| `uv run python scripts/check_translations.py` | Verify that `messages.pot` is 100% up to date |
| `uv run pybabel update -i messages.pot -d src/languages` | Update Arabic/English `.po` catalogs with new strings |
| `uv run pybabel compile -d src/languages` | Compile `.po` files into binary `.mo` catalogs |

## Implementation Procedures

### Step 1: Adding a New Localized UI Feature
1. Write the wxPython code in `src/gui/`, wrapping all text in `_("...")`.
2. Extract the updated strings:
   ```powershell
   uv run pybabel extract -F babel.cfg -k _ -o messages.pot .
   ```
3. Merge into the language catalogs:
   ```powershell
   uv run pybabel update -i messages.pot -d src/languages
   ```
4. Provide Arabic translations in `src/languages/ar/LC_MESSAGES/messages.po`.
5. Compile binary `.mo` files:
   ```powershell
   uv run pybabel compile -d src/languages
   ```
6. Run the verification script:
   ```powershell
   uv run python scripts/check_translations.py
   ```

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Concatenating strings (`_("A") + var`) | Cannot translate grammatically in Arabic | Use `_("A {var}").format(var=var)` |
| Modifying text without running pybabel | CI test fails on `check_translations.py` | Run extraction and commit `messages.pot` |
| Using positional `%s` without names | Word order cannot be swapped by translator | Use named placeholders `{filename}` |
| Forgetting to compile `.mo` after editing `.po` | App continues showing old translations | Run `pybabel compile` |

## Verification & Quality Gates

- **Freshness Check**: Run `uv run python scripts/check_translations.py`
- **Lint Check**: Run `uv run ruff check src/language_handler.py`
- **Manual Verification**:
  1. Open Settings (`Ctrl+P`) and switch language to Arabic (`العربية`).
  2. Restart HexPlayer.
  3. Verify menus, buttons, speech announcements, and dialog layouts render correctly in Arabic.
