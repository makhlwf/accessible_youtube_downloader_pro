import configparser
import os
import threading
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
    "audiooutputdevice": "",
    "debug": False,
    "background_monitoring": False,
    "playback_speed_step": 0.05,
    "eq_enabled": False,
    "eq_preamp": 0.0,
    "eq_bands": "0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0",
    "eq_preset": "Flat",
    "theme": "System Default",
}

_cache = {}
_config = configparser.ConfigParser()
_save_timer = None
_lock = threading.Lock()


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
        try:
            with open(settings_file, "w", encoding="utf-8") as file:
                config.write(file)
        except Exception:
            pass
    _load_cache()


def _load_cache():
    global _cache, _config
    settings_file = os.path.join(settings_path, "settings.ini")
    if not os.path.exists(settings_file):
        _cache = defaults.copy()
        return
    _config.read(settings_file, encoding="utf-8")
    if "settings" not in _config:
        _cache = defaults.copy()
        return
    for key in _config["settings"]:
        _cache[key] = string_to_bool(_config["settings"][key])
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


def save_settings():
    global _save_timer
    with _lock:
        if _save_timer:
            _save_timer.cancel()
            _save_timer = None
        settings_file = os.path.join(settings_path, "settings.ini")
        try:
            with open(settings_file, "w", encoding="utf-8") as file:
                _config.write(file)
        except Exception:
            pass


def config_set(key, value):
    global _save_timer
    _cache[key] = value
    with _lock:
        if "settings" not in _config:
            _config.add_section("settings")
        _config["settings"][key] = str(value)

        if _save_timer:
            _save_timer.cancel()
        _save_timer = threading.Timer(2.0, save_settings)
        _save_timer.start()
