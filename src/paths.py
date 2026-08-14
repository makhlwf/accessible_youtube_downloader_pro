import os
import sys


def get_app_path():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))


main_path = get_app_path()


def get_bundled_data_path():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return main_path


settings_root = os.getenv("APPDATA") or os.getenv("appdata")
if not settings_root:
    settings_root = os.path.expanduser("~/.HexPlayer")

settings_path = os.path.join(settings_root, "HexPlayer")
legacy_settings_paths = [
    os.path.join(settings_root, "accessible youtube downloader pro"),
    os.path.join(settings_root, "Accessible YouTube Downloader Pro"),
    os.path.join(settings_root, "accessible_youtube_downloader_pro"),
]
update_path = os.path.join(settings_path, "updates")
db_path = os.path.join(settings_path, "aHexPlayer.db")
js_runtime_path = os.path.join(settings_path, "js_runtime")
log_path = os.path.join(settings_path, "hexplayer.log")


def _get_yt_dlp_path():
    # Check multiple locations for yt_dlp.zip
    # 1. Check settings path (AppData) - preferred if updated by app
    roaming_path = os.path.join(settings_path, "yt_dlp.zip")
    if os.path.exists(roaming_path):
        return roaming_path

    # 2. Check application directory (for portable use)
    local_path = os.path.join(main_path, "yt_dlp.zip")
    if os.path.exists(local_path):
        return local_path

    # 3. Check bundled data path (if bundled with the exe)
    bundled_path = os.path.join(get_bundled_data_path(), "yt_dlp.zip")
    if os.path.exists(bundled_path):
        return bundled_path

    # Default to settings path for future downloads
    return roaming_path


yt_dlp_path = _get_yt_dlp_path()
deno_path = os.path.join(main_path, "deno.exe")
ffmpeg_path = os.path.join(get_bundled_data_path(), "ffmpeg.exe")
ffmpeg_dir = get_bundled_data_path()


def get_js_runtime_override_path(filename):
    return os.path.join(js_runtime_path, filename)


def get_js_runtime_file(filename):
    override_path = get_js_runtime_override_path(filename)
    if os.path.exists(override_path):
        return override_path

    main_file = os.path.join(main_path, filename)
    if os.path.exists(main_file):
        return main_file

    bundled_file = os.path.join(get_bundled_data_path(), filename)
    if os.path.exists(bundled_file):
        return bundled_file

    return main_file


def get_js_runtime_service_script():
    return get_js_runtime_file("service.js")


def get_js_runtime_config_path():
    return get_js_runtime_file("deno.json")


def get_js_runtime_lock_path():
    override_config = get_js_runtime_override_path("deno.json")
    override_lock = get_js_runtime_override_path("deno.lock")
    if os.path.exists(override_config) or os.path.exists(override_lock):
        return override_lock
    return get_js_runtime_file("deno.lock")


def get_writable_js_runtime_file(filename):
    os.makedirs(js_runtime_path, exist_ok=True)
    return os.path.join(js_runtime_path, filename)
