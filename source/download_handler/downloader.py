import os
import sys
import wx
import logging
from settings_handler import config_get
import paths
import utils
from wx.lib.newevent import NewEvent
from threading import Thread
from language_handler import _

logger = logging.getLogger(__name__)

ProgressChangedEvent, EVT_PROGRESS_CHANGED = NewEvent()


class Downloader:
    def __init__(
        self,
        url,
        path,
        downloading_format,
        monitor,
        status_label,
        convert=False,
        folder=False,
    ):
        # initializing class properties
        self.url = url
        self.path = path
        self.downloading_format = downloading_format
        self.monitor = monitor
        self.status_label = status_label
        self.convert = convert
        self.folder = folder

    def get_quality(self):
        qualities = {0: "96", 1: "128", 2: "192"}
        return qualities[int(config_get("conversion"))]

    def _progress_hook(self, d):
        if not self.monitor:
            return

        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "0%").replace("%", "").strip()
            try:
                percent = float(percent_str)
            except ValueError:
                percent = 0.0

            total = d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str", "")
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")

            wx.PostEvent(
                self.monitor,
                ProgressChangedEvent(
                    value=int(percent), total=total, speed=speed, eta=eta
                ),
            )

    def download(self):
        if not utils.YoutubeDL:
            logger.error("YoutubeDL library not loaded")
            return 1

        abs_ffmpeg_dir = os.path.abspath(paths.ffmpeg_dir)
        abs_ffmpeg_dir = os.path.normpath(abs_ffmpeg_dir).replace("\\", "/")

        env = os.environ.copy()
        env["PATH"] = (
            abs_ffmpeg_dir
            + os.pathsep
            + os.path.abspath(paths.main_path)
            + os.pathsep
            + env.get("PATH", "")
        )

        ydl_opts = {
            "nocheckcertificate": True,
            "outtmpl": os.path.join(self.path, "%(title)s.%(ext)s"),
            "format": self.downloading_format,
            "progress_hooks": [self._progress_hook],
            "ffmpeg_location": abs_ffmpeg_dir,
            "nocacheconfig": True,
            "extractor_args": {"youtube": {"player_client": ["tv"], "js_variant": "tv"}},
            "js_runtimes": {"deno": {}},
            "quiet": True,
            "no_warnings": True,
        }

        cookies_path = config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path

        if self.convert:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.get_quality(),
                }
            ]

        try:
            with utils.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            return 0
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return 1


def downloadAction(
    url,
    path,
    dlg,
    downloading_format,
    monitor,
    status_label,
    convert=False,
    folder=False,
):
    downloader = Downloader(
        url,
        path,
        downloading_format,
        monitor,
        status_label,
        convert=convert,
        folder=folder,
    )

    def on_progress(event):
        monitor.SetValue(event.value)
        status_label.SetString(0, _("نسبة التنزيل: {}%").format(event.value))
        if hasattr(event, "total") and event.total:
            status_label.SetString(1, _("حجم الملف الإجمالي: {}").format(event.total))
        else:
            status_label.SetString(1, _("حجم الملف الإجمالي: غير معروف"))
        if hasattr(event, "speed") and event.speed:
            status_label.SetString(2, _("سرعة التنزيل: {}").format(event.speed))
        else:
            status_label.SetString(2, _("سرعة التنزيل: غير معروفة"))
        if hasattr(event, "eta") and event.eta:
            status_label.SetString(3, _("الوقت المتبقي: {}").format(event.eta))
        else:
            status_label.SetString(3, _("الوقت المتبقي: غير معروف"))
        status_label.SetString(4, "")  # Clear the remaining amount string

    monitor.Bind(EVT_PROGRESS_CHANGED, on_progress)

    def download_thread():
        result = downloader.download()
        if result == 0:
            wx.MessageBox(_("اكتمل التنزيل بنجاح"), _("نجاح"), parent=dlg)
        else:
            wx.MessageBox(
                _("حدث خطأ أثناء التنزيل. يرجى التحقق من الرابط أو اتصالك بالإنترنت."),
                _("خطأ"),
                style=wx.ICON_ERROR,
                parent=dlg,
            )
        wx.CallAfter(dlg.Destroy)

    wx.CallAfter(dlg.Show)
    thread = Thread(target=download_thread)
    thread.start()
