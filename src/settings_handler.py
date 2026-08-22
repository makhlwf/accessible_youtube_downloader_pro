import configparser
import os
import threading

from language_handler import get_default_language
from paths import legacy_settings_paths, settings_path

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
    "browser_cookies_source": "",
    "defaultvideoquality": 4,
    "defaultaudioquality": 2,
    "audiooutputdevice": "",
    "player_fullscreen_default": False,
    "debug": False,
    "background_monitoring": False,
    "browser_integration": False,
    "playback_speed_step": 0.05,
    "eq_enabled": False,
    "eq_preamp": 0.0,
    "eq_bands": "0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0",
    "eq_preset": "Flat",
    "theme": "System Default",
    "player_client": "default",
}

_cache = {}
_default_key_map = {key.casefold(): key for key in defaults}
_save_timer = None
_lock = threading.Lock()


def _new_config():
    config = configparser.ConfigParser()
    config.optionxform = str
    return config


_config = _new_config()


def _canonical_key(key):
    return _default_key_map.get(str(key).casefold(), str(key))


def _settings_file(path):
    return os.path.join(path, "settings.ini")


def _candidate_settings_files():
    paths = [settings_path]
    for path in legacy_settings_paths:
        if path not in paths:
            paths.append(path)
    files = []
    for path in paths:
        settings_file = _settings_file(path)
        if os.path.exists(settings_file):
            files.append(settings_file)
    files.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return files


def _sync_config_from_cache():
    global _config
    _config = _new_config()
    _config.add_section("settings")
    written = set()
    for key in defaults:
        if key in _cache:
            _config["settings"][key] = str(_cache[key])
            written.add(key)
    for key, value in _cache.items():
        if key not in written:
            _config["settings"][key] = str(value)


def _write_settings_now():
    os.makedirs(settings_path, exist_ok=True)
    settings_file = _settings_file(settings_path)
    with open(settings_file, "w", encoding="utf-8") as file:
        _config.write(file)


def config_initialization():
    try:
        os.makedirs(settings_path, exist_ok=True)
    except Exception:
        pass
    _load_cache()
    try:
        _write_settings_now()
    except Exception:
        pass


def _load_cache():
    global _cache
    _cache = {}
    for settings_file in _candidate_settings_files():
        config = _new_config()
        config.read(settings_file, encoding="utf-8")
        if "settings" not in config:
            continue
        for key in config["settings"]:
            canonical_key = _canonical_key(key)
            if canonical_key not in _cache:
                _cache[canonical_key] = string_to_bool(config["settings"][key])

    for key, value in defaults.items():
        if key not in _cache:
            _cache[key] = value
    _sync_config_from_cache()


def string_to_bool(string):
    text = str(string).strip()
    if text.casefold() == "true":
        return True
    elif text.casefold() == "false":
        return False
    try:
        if text.isdigit():
            return int(text)
        return float(text)
    except ValueError:
        return string


def config_get(key):
    if not _cache:
        _load_cache()
    key = _canonical_key(key)
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
        try:
            _write_settings_now()
        except Exception:
            pass


def config_set(key, value):
    global _save_timer
    key = _canonical_key(key)
    _cache[key] = value
    with _lock:
        if "settings" not in _config:
            _config.add_section("settings")
        _config["settings"][key] = str(value)

        if _save_timer:
            _save_timer.cancel()
        _save_timer = threading.Timer(2.0, save_settings)
        _save_timer.start()
