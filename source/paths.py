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
yt_dlp_path = os.path.join(settings_path, "yt_dlp.py")
deno_path = os.path.join(main_path, "deno.exe")
ffmpeg_path = os.path.join(get_bundled_data_path(), "ffmpeg.exe")
ffmpeg_dir = get_bundled_data_path()
