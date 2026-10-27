import configparser
import io
import os
import tempfile
import threading
from time import monotonic

from language_handler import get_default_language, normalize_language_code
from paths import get_default_download_dir, legacy_settings_paths, settings_path

defaults = {
    "path": get_default_download_dir(),
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
    "eq_bands": "0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0",
    "eq_preset": "Flat",
    "theme": "System Default",
    "player_client": "default",
    "sponsorblock": False,
    "sponsorblock_categories": (
        "sponsor,selfpromo,interaction,intro,outro,preview,hook,filler,music_offtopic"
    ),
    "sponsorblock_notify": True,
    "sponsorblock_min_duration": 0.0,
    "sponsorblock_api_url": "https://sponsor.ajay.app",
    "pot_provider_enabled": True,
    "pot_provider_port": 4416,
    "search_suggestions": True,
    "welcome_completed": False,
    "force_original_audio": False,
    "preferred_audio_language": get_default_language(),
    "sleep_timer_last_minutes": 30,
    "discord_presence": True,
    "discord_client_id": "",
    "discord_show_details": True,
    "discord_show_buttons": True,
    "youtube_music_enabled": True,
    "youtube_music_default_audio_quality": 2,
    "youtube_music_filter_explicit": False,
    "youtube_music_lyrics": True,
    "youtube_music_home_sections": 5,
    "use_deno_backend": False,
}

_cache = {}
_default_key_map = {key.casefold(): key for key in defaults}
_lock = threading.RLock()
# Never acquire _io_lock while holding _lock: slow storage must not block edits.
_io_lock = threading.Lock()
_save_condition = threading.Condition(_lock)
_save_thread = None
_save_deadline = None
_SAVE_DELAY = 2.0
_dirty = False
_revision = 0


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


def _write_settings_now(contents):
    """Replace the file only after a complete, flushed same-directory write."""
    os.makedirs(settings_path, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=settings_path,
            prefix=".settings-",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        # Close the temporary file first, including on Windows.
        os.replace(temporary_path, _settings_file(settings_path))
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def config_initialization():
    _load_cache()
    save_settings()


def _ensure_cache_loaded():
    with _lock:
        if _cache:
            return
    _load_cache(only_if_empty=True)


def _load_cache(*, only_if_empty=False):
    global _cache, _dirty, _revision, _save_deadline
    with _io_lock:
        with _lock:
            # Startup initializes more than once. Pending (or failed) writes
            # must be flushed from memory, not replaced with stale disk values.
            if _cache and (only_if_empty or _dirty):
                return
            revision = _revision

        # Read into local state, never exposing a partially loaded cache.
        cache = {}
        for settings_file in _candidate_settings_files():
            config = _new_config()
            config.read(settings_file, encoding="utf-8")
            if "settings" not in config:
                continue
            for key in config["settings"]:
                canonical_key = _canonical_key(key)
                if canonical_key not in cache:
                    cache[canonical_key] = string_to_bool(config["settings"][key])

        for key, value in defaults.items():
            if key not in cache:
                cache[key] = value
        cache["lang"] = normalize_language_code(cache["lang"])
        with _save_condition:
            # An explicit reload must not discard edits made during its disk read.
            if revision != _revision:
                return
            _cache = cache
            _sync_config_from_cache()
            _revision += 1
            _dirty = False
            _save_deadline = None
            _save_condition.notify_all()


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
    _ensure_cache_loaded()
    key = _canonical_key(key)
    with _lock:
        if key == "lang":
            raw = _cache.get(key, defaults.get(key))
            normalized = normalize_language_code(raw)
            if key not in _cache or normalized != raw:
                config_set(key, normalized)
            return normalized
        if key in _cache:
            return _cache[key]
        # Fallback to defaults if key not found.
        value = defaults.get(key)
        if value is not None:
            config_set(key, value)
        return value


def _flush_settings(*, pending_only=False):
    global _dirty, _save_deadline
    # Take the snapshot AFTER acquiring the I/O lock, so an older background
    # save can never replace a newer explicit save with an obsolete snapshot.
    with _io_lock:
        try:
            with _save_condition:
                if pending_only and (
                    _save_deadline is None or _save_deadline > monotonic()
                ):
                    return
                _save_deadline = None
                _save_condition.notify_all()
                contents = io.StringIO()
                _config.write(contents)
                # Edits during the write make the cache dirty and queue another
                # flush. A failed write also leaves it eligible for retry.
                _dirty = False
            _write_settings_now(contents.getvalue())
        except Exception:
            with _lock:
                _dirty = True


def save_settings():
    """Synchronously persist the latest snapshot, including at application exit.

    Wait for any in-flight write and consume the pending debounce. Edits made
    during this write remain queued; callers should stop editing before exit.
    """
    _ensure_cache_loaded()
    _flush_settings()


def _save_worker():
    global _save_thread
    while True:
        with _save_condition:
            if _save_deadline is None:
                _save_thread = None
                return
            remaining = _save_deadline - monotonic()
            if remaining > 0:
                _save_condition.wait(timeout=remaining)
                continue
        _flush_settings(pending_only=True)


def _schedule_save_locked():
    """Coalesce edits into a bounded window; the caller holds _lock."""
    global _save_deadline, _save_thread
    if _save_deadline is None:
        # Do not restart the window on every slider tick. Sustained input must
        # neither create a thread per edit nor postpone persistence forever.
        _save_deadline = monotonic() + _SAVE_DELAY
        _save_condition.notify_all()
    if _save_thread is None:
        _save_thread = threading.Thread(
            target=_save_worker, name="settings-save", daemon=True
        )
        _save_thread.start()


def config_set(key, value):
    global _dirty, _revision
    key = _canonical_key(key)
    if key == "lang":
        value = normalize_language_code(value)
    _ensure_cache_loaded()
    with _lock:
        if key in _cache and type(_cache[key]) is type(value) and _cache[key] == value:
            # A no-op must not extend the window, but can retry a failed flush.
            if _dirty and _save_deadline is None:
                _schedule_save_locked()
            return
        if "settings" not in _config:
            _config.add_section("settings")
        # Validate/serialize before updating the cache to keep both consistent.
        _config["settings"][key] = str(value)
        _cache[key] = value
        _revision += 1
        _dirty = True
        _schedule_save_locked()
