import logging
import os
import re
import time
from threading import Thread

import wx
from wx.lib.newevent import NewEvent

import paths
import utils
from language_handler import _
from settings_handler import config_get

logger = logging.getLogger(__name__)

ProgressChangedEvent, EVT_PROGRESS_CHANGED = NewEvent()


class DownloadCancelled(Exception):
    pass


ANSI_RE = re.compile(r"(?:\x1b\[[0-?]*[ -/]*[@-~]|\[[0-9;]*m)")


def clean_progress_text(value):
    if value is None:
        return ""
    return ANSI_RE.sub("", str(value)).replace("\r", "").strip()


AUDIO_KBPS_FORMAT_MAP = {
    96: (
        "bestaudio[abr=96][ext=m4a]/bestaudio[abr=96]/bestaudio[ext=m4a]/bestaudio/best"
    ),
    128: (
        "bestaudio[abr=128][ext=m4a]/bestaudio[abr=128]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
    192: (
        "bestaudio[abr=192][ext=m4a]/bestaudio[abr=192]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
    320: (
        "bestaudio[abr=320][ext=m4a]/bestaudio[abr=320]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
}

AUDIO_KBPS_SORTED = sorted(AUDIO_KBPS_FORMAT_MAP.keys())


def _fallback_format_for_kbps(kbps):
    for candidate in reversed(AUDIO_KBPS_SORTED):
        if candidate <= kbps:
            return AUDIO_KBPS_FORMAT_MAP[candidate]
    return AUDIO_KBPS_FORMAT_MAP[AUDIO_KBPS_SORTED[0]]


def get_audio_download_format(convert=False, kbps=None):
    if convert:
        return "bestaudio/best"
    if kbps is None:
        kbps = int(config_get("conversion"))
    kbps = int(kbps)
    if kbps in AUDIO_KBPS_FORMAT_MAP:
        return AUDIO_KBPS_FORMAT_MAP[kbps]
    return _fallback_format_for_kbps(kbps)


def get_video_download_format(quality=None):
    if quality:
        return (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}][ext=mp4]/best[height<={quality}]/best"
        )
    return (
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
    )


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
        cancel_checker=None,
        kbps=None,
    ):
        # initializing class properties
        self.url = url
        self.path = path
        self.downloading_format = downloading_format
        self.monitor = monitor
        self.status_label = status_label
        self.convert = convert
        self.folder = folder
        self.cancelled = False
        self.cancel_checker = cancel_checker
        self.last_file = None
        self.started_at = None
        self.kbps = kbps

    def get_quality(self):
        qualities = {0: "96", 1: "128", 2: "192", 3: "320"}
        return qualities[int(config_get("conversion"))]

    def cancel(self):
        self.cancelled = True

    def _is_cancelled(self):
        return self.cancelled or (
            self.cancel_checker is not None and self.cancel_checker()
        )

    def _remember_file(self, path):
        if path and os.path.exists(path):
            self.last_file = path

    def _hook_file(self, data):
        if isinstance(data, str):
            return data
        if not isinstance(data, dict):
            return None
        info = data.get("info_dict") or {}
        return (
            data.get("filepath")
            or data.get("filename")
            or info.get("filepath")
            or info.get("_filename")
        )

    def _after_move_hook(self, data):
        self._remember_file(self._hook_file(data))

    def _postprocessor_hook(self, data):
        if isinstance(data, dict) and data.get("status") not in (None, "finished"):
            return
        self._remember_file(self._hook_file(data))

    def _find_latest_downloaded_file(self):
        if not os.path.isdir(self.path):
            return None
        latest_file = None
        latest_time = 0
        for root, dirs, files in os.walk(self.path):
            for filename in files:
                path = os.path.join(root, filename)
                try:
                    modified = os.path.getmtime(path)
                except OSError:
                    continue
                if self.started_at is not None and modified < self.started_at - 2:
                    continue
                if modified > latest_time:
                    latest_time = modified
                    latest_file = path
        return latest_file

    def _progress_hook(self, d):
        if self._is_cancelled():
            raise DownloadCancelled()
        if not self.monitor:
            return

        if d.get("status") == "downloading":
            percent_str = clean_progress_text(d.get("_percent_str", "0%")).replace(
                "%", ""
            )
            try:
                percent = float(percent_str)
            except ValueError:
                percent = 0.0

            total = clean_progress_text(
                d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str", "")
            )
            downloaded = clean_progress_text(d.get("_downloaded_bytes_str", ""))
            speed = clean_progress_text(d.get("_speed_str", ""))
            eta = clean_progress_text(d.get("_eta_str", ""))

            wx.PostEvent(
                self.monitor,
                ProgressChangedEvent(
                    value=int(percent),
                    total=total,
                    downloaded=downloaded,
                    speed=speed,
                    eta=eta,
                ),
            )

    def _base_options(self, use_cookies=True):
        abs_ffmpeg_dir = os.path.abspath(paths.ffmpeg_dir)
        abs_ffmpeg_dir = os.path.normpath(abs_ffmpeg_dir).replace("\\", "/")

        runtime_paths = (abs_ffmpeg_dir, os.path.abspath(paths.main_path))
        current_path = os.environ.get("PATH", "")
        missing_paths = (
            path for path in runtime_paths if path not in current_path.split(os.pathsep)
        )
        prepend_path = os.pathsep.join(missing_paths)
        if prepend_path:
            os.environ["PATH"] = prepend_path + os.pathsep + current_path

        ydl_opts = {
            "nocheckcertificate": True,
            "outtmpl": os.path.join(self.path, "%(title)s.%(ext)s"),
            "format": self._effective_format(),
            "noplaylist": not self.folder,
            "continuedl": True,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "post_hooks": [self._after_move_hook],
            "ffmpeg_location": abs_ffmpeg_dir,
            "nocacheconfig": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                    "js_variant": "main",
                }
            },
            "js_runtimes": {"deno": {}},
            "quiet": True,
            "no_warnings": True,
        }

        cookies_path = config_get("cookiespath")
        if use_cookies and cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path

        if self.convert:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.get_quality(),
                }
            ]
        return ydl_opts

    def _effective_format(self):
        if self.convert:
            return get_audio_download_format(convert=True)
        if self.downloading_format == "bestaudio[ext=m4a]":
            return get_audio_download_format(kbps=self.kbps)
        if self.downloading_format == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4":
            return get_video_download_format()
        return self.downloading_format

    def _is_cookie_error(self, error):
        message = str(error).lower()
        return any(
            part in message
            for part in (
                "cookie",
                "cookies",
                "dpapi",
                "decrypt",
                "could not copy",
                "database is locked",
                "unable to open database file",
            )
        )

    def download(self, use_cookies=True):
        if not utils.YoutubeDL:
            logger.error("YoutubeDL library not loaded")
            return RuntimeError("missing yt-dlp binary")

        if self._is_cancelled():
            return DownloadCancelled()

        os.makedirs(self.path, exist_ok=True)
        self.started_at = time.time()
        ydl_opts = self._base_options(use_cookies=use_cookies)

        try:
            with utils.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            if not self.last_file or not os.path.exists(self.last_file):
                self.last_file = self._find_latest_downloaded_file()
            return 0
        except DownloadCancelled as e:
            logger.info("Download cancelled")
            return e
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return e

    def download_with_cookie_fallback(self):
        result = self.download(use_cookies=True)
        if isinstance(result, Exception) and self._is_cookie_error(result):
            logger.warning("Cookie-based download failed; retrying without cookies")
            return self.download(use_cookies=False)
        return result


def diagnose_download_error(error) -> str:
    err_str = str(error) if error is not None else ""
    err_lower = err_str.lower()

    if (
        (not utils.YoutubeDL and not err_str)
        or "missing yt-dlp" in err_lower
        or "ytdl_missing" in err_lower
    ):
        return utils.format_bilingual_message(
            _("لم يتم العثور على مكتبة yt-dlp."),
            _("yt-dlp library was not found."),
        )
    if any(
        k in err_lower
        for k in (
            "permission denied",
            "access is denied",
            "access denied",
            "no space left",
            "disk full",
            "errno 28",
            "permissionerror",
            "winerror 5",
            "winerror 32",
        )
    ):
        return utils.format_bilingual_message(
            _("تعذر الكتابة على القرص (تم رفض الوصول أو القرص ممتلئ)."),
            _("Permission denied or disk full. Could not write to disk."),
        )
    if any(
        k in err_lower
        for k in (
            "timeout",
            "timed out",
            "connection",
            "network",
            "socket",
            "http error",
            "urlerror",
            "dropped",
            "read timed out",
            "connect timeout",
        )
    ):
        return utils.format_bilingual_message(
            _(
                "تعذر الاتصال بالشبكة أو انتهت مهلة الإرسال. يرجى التحقق من اتصال الإنترنت."
            ),
            _(
                "Network timeout or connection dropped. Please check your internet connection."
            ),
        )
    if err_str:
        return utils.format_bilingual_message(
            _("حدث خطأ أثناء التنزيل: {}").format(err_str),
            _("Download error occurred: {}").format(err_str),
        )
    return utils.format_bilingual_message(
        _("حدث خطأ أثناء التنزيل. يرجى التحقق من الرابط أو اتصالك بالإنترنت."),
        _("Download error occurred. Please check the link or internet connection."),
    )


def downloadAction(
    url,
    path,
    dlg,
    downloading_format,
    monitor,
    status_label,
    convert=False,
    folder=False,
    kbps=None,
):
    if not utils.check_yt_dlp(wx.GetApp().GetTopWindow()):
        dlg.Destroy()
        return False

    downloader = Downloader(
        url,
        path,
        downloading_format,
        monitor,
        status_label,
        convert=convert,
        folder=folder,
        cancel_checker=dlg.is_cancelled if hasattr(dlg, "is_cancelled") else None,
        kbps=kbps,
    )
    if hasattr(dlg, "set_cancel_callback"):
        dlg.set_cancel_callback(downloader.cancel)

    def on_progress(event):
        monitor.SetValue(event.value)
        status_label.SetString(0, _("نسبة التنزيل: {}%").format(event.value))
        if hasattr(event, "total") and event.total:
            status_label.SetString(1, _("حجم الملف الإجمالي: {}").format(event.total))
        else:
            status_label.SetString(1, _("حجم الملف الإجمالي: غير معروف"))
        if hasattr(event, "downloaded") and event.downloaded:
            status_label.SetString(
                2, _("مقدار الحجم الذي تم تنزيله: {}").format(event.downloaded)
            )
        else:
            status_label.SetString(2, _("مقدار الحجم الذي تم تنزيله: غير معروف"))
        if hasattr(event, "speed") and event.speed:
            status_label.SetString(4, _("سرعة التنزيل: {}").format(event.speed))
        else:
            status_label.SetString(4, _("سرعة التنزيل: غير معروفة"))
        if hasattr(event, "eta") and event.eta:
            status_label.SetString(3, _("الوقت المتبقي: {}").format(event.eta))
        else:
            status_label.SetString(3, _("الوقت المتبقي: غير معروف"))

    monitor.Bind(EVT_PROGRESS_CHANGED, on_progress)
    dlg.Show()

    def download_thread():
        result = None
        for attempt in range(3):
            result = downloader.download_with_cookie_fallback()
            if result == 0 or isinstance(result, DownloadCancelled):
                break
            logger.warning("Download attempt %s failed for %s", attempt + 1, url)

        def finish_download():
            if hasattr(dlg, "mark_finished"):
                dlg.mark_finished()
            if result == 0:
                parent = (
                    dlg.GetParent() if dlg is not None else wx.GetApp().GetTopWindow()
                )
                file_path = downloader.last_file
                folder_path = path if folder else None
                dlg.Destroy()
                from gui.download_complete_dialog import show_download_complete

                show_download_complete(
                    parent, file_path=file_path, folder_path=folder_path
                )
            elif isinstance(result, DownloadCancelled):
                wx.MessageBox(_("تم إلغاء التنزيل"), _("إلغاء"), parent=dlg)
                dlg.Destroy()
            else:
                err_msg = diagnose_download_error(result)
                utils.show_error(
                    err_msg,
                    result if isinstance(result, Exception) else None,
                    parent=dlg,
                )
                dlg.Destroy()

        wx.CallAfter(finish_download)

    thread = Thread(target=download_thread)
    thread.daemon = True
    thread.start()
    return True
