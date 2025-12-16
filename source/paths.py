import os
import sys

def get_app_path():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))

main_path = get_app_path()

settings_path = os.path.join(os.getenv("appdata"), "accessible youtube downloader pro")
update_path = os.path.join(settings_path, "updates")
db_path = os.path.join(settings_path, "accessible_youtube_downloader_pro.db")
yt_dlp_path = os.path.join(main_path, "yt-dlp.exe")
