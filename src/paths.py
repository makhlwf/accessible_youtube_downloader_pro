import os
import shlex
import shutil
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


def _xdg_root(variable, fallback):
    value = os.environ.get(variable, "")
    return value if os.path.isabs(value) else os.path.expanduser(fallback)


def get_config_root():
    return _xdg_root("XDG_CONFIG_HOME", "~/.config")


def get_data_root():
    return _xdg_root("XDG_DATA_HOME", "~/.local/share")


def _get_settings_root():
    if sys.platform == "win32":
        return (
            os.getenv("APPDATA")
            or os.getenv("appdata")
            or os.path.expanduser("~/.HexPlayer")
        )
    return get_data_root()


settings_root = _get_settings_root()
portable = os.path.isfile(os.path.join(main_path, "portable.dat"))
settings_path = (
    os.path.join(main_path, "data")
    if portable
    else os.path.join(settings_root, "HexPlayer")
)
legacy_settings_paths = [
    os.path.join(settings_root, "accessible youtube downloader pro"),
    os.path.join(settings_root, "Accessible YouTube Downloader Pro"),
    os.path.join(settings_root, "accessible_youtube_downloader_pro"),
]
if sys.platform != "win32" and not portable:
    legacy_settings_paths.append(os.path.expanduser("~/.HexPlayer/HexPlayer"))
update_path = os.path.join(settings_path, "updates")
db_path = os.path.join(settings_path, "aHexPlayer.db")
js_runtime_path = os.path.join(settings_path, "js_runtime")
log_path = os.path.join(settings_path, "hexplayer.log")
pot_provider_dir = os.path.join(settings_path, "pot_provider")
pot_provider_exe = os.path.join(
    pot_provider_dir, "bgutil-pot.exe" if os.name == "nt" else "bgutil-pot"
)
pot_provider_plugins_dir = os.path.join(pot_provider_dir, "plugins")
pot_provider_version_file = os.path.join(pot_provider_dir, "version.json")


def get_default_download_dir():
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    if sys.platform == "linux":
        try:
            with open(
                os.path.join(get_config_root(), "user-dirs.dirs"), encoding="utf-8"
            ) as stream:
                for line in stream:
                    key, separator, value = line.partition("=")
                    if separator and key.strip() == "XDG_DOWNLOAD_DIR":
                        parts = shlex.split(value, comments=True)
                        if len(parts) == 1:
                            candidate = (
                                parts[0].replace("${HOME}", home).replace("$HOME", home)
                            )
                            if os.path.isabs(candidate):
                                downloads = candidate
                        break
        except OSError, ValueError:
            pass
    return os.path.join(downloads, "HexPlayer")


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
deno_install_path = os.path.join(
    main_path if sys.platform == "win32" else js_runtime_path,
    "deno.exe" if sys.platform == "win32" else "deno",
)
deno_path = deno_install_path


def get_deno_path():
    candidates = [deno_path]
    if sys.platform != "win32":
        candidates.extend(
            [
                os.path.join(main_path, "deno"),
                os.path.join(get_bundled_data_path(), "deno"),
                shutil.which("deno"),
            ]
        )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return deno_path


ffmpeg_path = os.path.join(
    get_bundled_data_path(), "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
)
if sys.platform != "win32" and not os.path.isfile(ffmpeg_path):
    ffmpeg_path = shutil.which("ffmpeg") or ffmpeg_path
ffmpeg_dir = os.path.dirname(ffmpeg_path)


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
