import gettext
import ctypes
import locale
from collections import OrderedDict
import wx


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


def get_default_language():
    windll = ctypes.windll.kernel32
    lang_id = windll.GetUserDefaultUILanguage()
    try:
        language = locale.windows_locale[lang_id].split("_")[0]
        if language not in supported_languages.values():
            language = "en"
    except:
        language = "en"
    return language


def init_translation(domain):
    from settings_handler import config_get

    try:
        tr = gettext.translation(
            domain, localedir="languages", languages=[config_get("lang")]
        )
    except:
        tr = gettext.translation(domain, fallback=True)
    tr.install()