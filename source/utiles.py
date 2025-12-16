import re
from threading import Thread
from settings_handler import config_get
from download_handler.downloader import downloadAction
import requests
import wx
import application
import paths
from gui.update_dialog import UpdateDialog
import subprocess
import json
import os


def download_yt_dlp():
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    wx.CallAfter(
        UpdateDialog,
        wx.GetApp().GetTopWindow(),
        url,
        paths.yt_dlp_path,
        _("جاري تنزيل yt-dlp"),
    )


def update_yt_dlp():
    msg = wx.MessageBox(
        _("سيتم الآن البحث عن تحديث لبرنامج yt-dlp وتنزيله إن وجد, هل تريد المتابعة؟"),
        _("تحديث"),
        style=wx.YES_NO | wx.ICON_INFORMATION,
        parent=wx.GetApp().GetTopWindow(),
    )
    if msg == wx.YES:
        download_yt_dlp()


def check_yt_dlp():
    if not os.path.exists(paths.yt_dlp_path):
        msg = wx.MessageBox(
            _("لم يتم العثور على yt-dlp.exe, هل تريد تنزيله الآن؟"),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()
            return True
        return False
    return True


class Stream:
    def __init__(self, title, url):
        self.title = title
        self.url = url


def get_media_info(url):
    if not os.path.exists(paths.yt_dlp_path):
        return None
    try:
        command = [paths.yt_dlp_path, "-j", url]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return None


def get_audio_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    audio_streams = [
        f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"
    ]
    stream = None
    for s in reversed(audio_streams):
        if s.get("ext") == "webm":
            stream = s
            break
    if stream is None:
        best_audio = sorted(audio_streams, key=lambda x: x.get("abr", 0), reverse=True)
        if best_audio:
            stream = best_audio[0]
    if stream:
        return Stream(title, stream["url"])
    return None


def get_video_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    video_streams = [f for f in formats if f.get("vcodec") != "none"]
    stream = None
    for s in video_streams:
        if s.get("ext") == "mp4" and f"{s.get('width')}x{s.get('height')}" == "640x360":
            stream = s
            break
    if stream is None:
        # Fallback to best available stream
        video_streams = sorted(
            video_streams,
            key=lambda x: x.get("width", 0) * x.get("height", 0),
            reverse=True,
        )
        if video_streams:
            stream = video_streams[0]

    if stream:
        return Stream(title, stream["url"])
    return None


def time_formatting(total_seconds):
    if total_seconds is None:
        return ""
    try:
        total_seconds = int(total_seconds)
    except (ValueError, TypeError):
        return ""

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours > 0:
        if hours == 1:
            parts.append(_("ساعة واحدة"))
        elif hours == 2:
            parts.append(_("ساعتان"))
        elif 3 <= hours <= 10:
            parts.append(_("{} ساعات").format(hours))
        else:
            parts.append(_("{} ساعة").format(hours))

    if minutes > 0:
        if minutes == 1:
            parts.append(_("دقيقة واحدة"))
        elif minutes == 2:
            parts.append(_("دقيقتان"))
        elif 3 <= minutes <= 10:
            parts.append(_("{} دقائق").format(minutes))
        else:
            parts.append(_("{} دقيقة").format(minutes))

    if (
        seconds > 0 or (not parts and total_seconds == 0)
    ):  # Include seconds if no other parts, or if it's the only part and total_seconds is 0
        if seconds == 1:
            parts.append(_("ثانية واحدة"))
        elif seconds == 2:
            parts.append(_("ثانيتين"))
        elif 3 <= seconds <= 10:
            parts.append(_("{} ثواني").format(seconds))
        else:
            parts.append(_("{} ثانية").format(seconds))

    if not parts and total_seconds == 0:
        return _("0 ثانية")

    return _(" و").join(parts)


def time_to_seconds(time_str):
    if not isinstance(time_str, str):
        return None
    parts = time_str.split(":")
    total_seconds = 0
    try:
        if len(parts) == 3:  # HH:MM:SS
            total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:  # MM:SS
            total_seconds = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:  # SS
            total_seconds = int(parts[0])
        else:
            return None  # Invalid format
    except ValueError:
        return None  # Handle cases where parts are not valid integers
    return total_seconds


def youtube_regexp(string):
    pattern = re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
    )  # youtube links regular expression pattern
    return pattern.search(string)


def check_for_updates(quiet=False):
    url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update_info.json"
    try:
        r = requests.get(url)
        if r.status_code != 200:
            wx.MessageBox(
                _(
                    "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                ),
                _("خطأ"),
                parent=wx.GetApp().GetTopWindow(),
                style=wx.ICON_ERROR,
            ) if not quiet else None
            return
        info = r.json()
        if application.version != info["version"]:
            print(info)
            message = wx.MessageBox(
                _("هناك تحديث جديد متوفر. هل ترغب في تنزيله الآن؟"),
                _("تحديث جديد"),
                parent=wx.GetApp().GetTopWindow(),
                style=wx.YES_NO,
            )
            url = info["url"]
            if message == wx.YES:
                from gui.update_dialog import UpdateDialog

                wx.CallAfter(UpdateDialog, wx.GetApp().GetTopWindow(), url)
            return
        wx.MessageBox(
            _("أنت تعمل الآن على آخر تحديث متوفر من التطبيق"),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        ) if not quiet else None
    except requests.ConnectionError:
        wx.MessageBox(
            _(
                "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
            ),
            _("خطأ"),
            parent=wx.GetApp().GetTopWindow(),
            style=wx.ICON_ERROR,
        ) if not quiet else None
