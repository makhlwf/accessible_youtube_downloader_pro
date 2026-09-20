import builtins
import ctypes
import gettext
import locale
import os
import sys
from collections import OrderedDict

import wx


def _(text):
    return getattr(builtins, "_", lambda x: x)(text)


supported_languages = OrderedDict(
    {
        "العربية": "ar",
        "English": "en",
    }
)

languages = list(supported_languages.values())

codes = {
    "ar": wx.LANGUAGE_ARABIC,
    "en": wx.LANGUAGE_ENGLISH,
}
lang_id = wx.LANGUAGE_ARABIC


def normalize_language_code(lang):
    """Normalize language name or code to a valid 2-letter ISO code."""
    if not lang:
        return "en"
    text = str(lang).strip()
    if text in supported_languages.values():
        return text
    if text in supported_languages:
        return supported_languages[text]
    lower = text.casefold()
    if lower in ("ar", "arabic") or "عرب" in text:
        return "ar"
    if lower in ("en", "english"):
        return "en"
    prefix = lower.split("_")[0].split("-")[0]
    if len(prefix) == 2 and prefix.isalpha():
        return prefix
    return "en"


def get_default_language():
    language = "en"
    try:
        if sys.platform == "win32":
            windll = ctypes.windll.kernel32
            lang_id = windll.GetUserDefaultUILanguage()
            language = locale.windows_locale[lang_id].split("_")[0]
        else:
            lang_code = (
                os.environ.get("LC_ALL")
                or os.environ.get("LC_MESSAGES")
                or os.environ.get("LANG")
                or "en"
            )
            language = lang_code.split(".")[0].split("_")[0]
            if language == "C":
                language = "en"
    except Exception:
        language = "en"
    if language not in supported_languages.values():
        language = "en"
    return language


def init_translation(domain):
    import os

    from paths import get_bundled_data_path
    from settings_handler import config_get

    localedir = os.path.join(get_bundled_data_path(), "languages")
    try:
        lang_code = normalize_language_code(config_get("lang"))
        tr = gettext.translation(domain, localedir=localedir, languages=[lang_code])
    except Exception:
        tr = gettext.translation(domain, fallback=True)
    tr.install()
