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


settings_path = os.path.join(os.getenv("appdata") or os.path.expanduser("~/.HexPlayer"), "HexPlayer")
update_path = os.path.join(settings_path, "updates")
db_path = os.path.join(settings_path, "aHexPlayer.db")
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
