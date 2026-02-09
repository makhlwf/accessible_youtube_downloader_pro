import configparser
import os
from language_handler import get_default_language
from paths import settings_path

# settings_path = os.path.join(os.getenv("appdata"), "accessible youtube downloader pro")

defaults = {
    "path": f"{os.getenv('USERPROFILE')}\\downloads\\HexPlayer",
    "defaultaudio": 0,
    "lang": get_default_language(),
    "autodetect": True,
    "checkupdates": True,
    "autoload": True,
    "seek": 5,
    "conversion": 1,
    "repeatTracks": False,
    "autonext": False,
    "defaultformat": 0,
    "volume": 100,
    "continue": True,
    "cookiespath": "",
    "defaultvideoquality": 4,
    "defaultaudioquality": 2,
}

_cache = {}


def config_initialization():
    try:
        os.makedirs(settings_path, exist_ok=True)
    except Exception:
        pass
    settings_file = os.path.join(settings_path, "settings.ini")
    if not os.path.exists(settings_file):
        config = configparser.ConfigParser()
        config.add_section("settings")
        for key, value in defaults.items():
            config["settings"][key] = str(value)
        with open(settings_file, "w", encoding="utf-8") as file:
            config.write(file)
    _load_cache()


def _load_cache():
    global _cache
    settings_file = os.path.join(settings_path, "settings.ini")
    if not os.path.exists(settings_file):
        _cache = defaults.copy()
        return
    config = configparser.ConfigParser()
    config.read(settings_file, encoding="utf-8")
    if "settings" not in config:
        _cache = defaults.copy()
        return
    for key in config["settings"]:
        _cache[key] = string_to_bool(config["settings"][key])
    # Ensure all defaults are present
    for key, value in defaults.items():
        if key not in _cache:
            _cache[key] = value


def string_to_bool(string):
    if string == "True":
        return True
    elif string == "False":
        return False
    try:
        if string.isdigit():
            return int(string)
        return float(string)
    except ValueError:
        return string


def config_get(key):
    if not _cache:
        _load_cache()
    if key in _cache:
        return _cache[key]
    # Fallback to defaults if key not found
    val = defaults.get(key)
    if val is not None:
        config_set(key, val)
    return val


def config_set(key, value):
    _cache[key] = value
    config = configparser.ConfigParser()
    settings_file = os.path.join(settings_path, "settings.ini")
    config.read(settings_file, encoding="utf-8")
    if "settings" not in config:
        config.add_section("settings")
    config["settings"][key] = str(value)
    with open(settings_file, "w", encoding="utf-8") as file:
        config.write(file)
