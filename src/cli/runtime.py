"""Shared runtime helpers for the HexPlayer CLI.

Provides one-time headless bootstrap (settings + translations), an output
emitter that supports both human-readable text and ``--json`` output, an
asyncio runner, and dependency guards that never trigger GUI dialogs.
"""

import asyncio
import gettext
import json
import os
import sys

_BOOTSTRAPPED = False


def bootstrap(lang=None):
    """Initialise settings and translations for headless use.

    ``lang`` optionally overrides the interface language for this invocation
    only (it is not persisted to settings).
    """
    global _BOOTSTRAPPED

    # Ensure stdout/stderr can carry Arabic and other non-ASCII text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    import settings_handler

    try:
        settings_handler.config_initialization()
    except Exception:
        pass

    _install_translation(lang)
    _BOOTSTRAPPED = True


def _install_translation(lang=None):
    """Install the gettext ``_`` builtin for the chosen language.

    Mirrors ``language_handler.init_translation`` but allows a per-invocation
    language override without writing it back to settings.
    """
    from language_handler import normalize_language_code
    from paths import get_bundled_data_path
    from settings_handler import config_get

    if lang:
        lang_code = normalize_language_code(lang)
    else:
        lang_code = normalize_language_code(config_get("lang"))

    localedir = os.path.join(get_bundled_data_path(), "languages")
    try:
        translation = gettext.translation(
            "HexPlayer", localedir=localedir, languages=[lang_code]
        )
    except Exception:
        translation = gettext.translation("HexPlayer", fallback=True)
    translation.install()


def run_async(coro):
    """Run an async coroutine to completion on a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


class Emitter:
    """Writes command results as either human text or JSON.

    Text lines and structured data are supplied together by each command so
    the same handler serves both output modes.
    """

    def __init__(self, json_mode=False):
        self.json_mode = json_mode

    def result(self, data, text_lines=None):
        if self.json_mode:
            self._dump({"ok": True, "data": data})
            return
        if text_lines is None:
            text_lines = []
        elif isinstance(text_lines, str):
            text_lines = [text_lines]
        for line in text_lines:
            print(line)

    def message(self, text, data=None):
        """A simple success message (e.g. after a mutating command)."""
        if self.json_mode:
            payload = {"ok": True, "message": text}
            if data is not None:
                payload["data"] = data
            self._dump(payload)
        else:
            print(text)

    def error(self, text, code="error"):
        if self.json_mode:
            self._dump({"ok": False, "error": text, "code": code}, stream=sys.stderr)
        else:
            print(text, file=sys.stderr)

    def _dump(self, payload, stream=None):
        json.dump(payload, stream or sys.stdout, ensure_ascii=False, indent=2)
        (stream or sys.stdout).write("\n")


def deno_available():
    """True when the Deno runtime is installed (no GUI prompt)."""
    import paths

    return os.path.exists(paths.get_deno_path())


def cookies_available():
    """True when a configured cookies file exists on disk."""
    from settings_handler import config_get

    cookies_path = config_get("cookiespath")
    return bool(cookies_path and os.path.exists(cookies_path))


def require_deno(emitter):
    """Emit a localized error and return False when Deno is missing."""
    from language_handler import _

    if deno_available():
        return True
    emitter.error(
        _(
            "هذه الميزة تتطلب تثبيت أداة Deno. ثبّتها عبر الأمر: hexplayer deps update --deno"
        ),
        code="deno_missing",
    )
    return False


def require_cookies(emitter):
    """Emit a localized error and return False when cookies are missing."""
    from language_handler import _

    if cookies_available():
        return True
    emitter.error(
        _(
            "هذه الميزة تتطلب ملف كوكيز صالح. اضبطه عبر الأمر: hexplayer cookies set <المسار>"
        ),
        code="cookies_missing",
    )
    return False
