import subprocess
import wx
from settings_handler import config_get
import paths
import re
from wx.lib.newevent import NewEvent
from threading import Thread

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
        self.process = None

    def get_quality(self):
        qualities = {0: "96", 1: "128", 2: "192"}
        return qualities[int(config_get("conversion"))]

    def progress_parser(self, line):
        if not self.monitor:
            return
        
        match = re.search(r"\[download\]\s+([0-9\.]+)% of\s+(.*?)\s+at\s+(.*?)\s+ETA\s+(.*)", line)
        if match:
            percent = float(match.group(1))
            total = match.group(2).strip()
            speed = match.group(3).strip()
            eta = match.group(4).strip()
            wx.PostEvent(self.monitor, ProgressChangedEvent(value=int(percent), total=total, speed=speed, eta=eta))
        else:
            match = re.search(r"\[download\]\s+([0-9\.]+)%", line)
            if match:
                percent = float(match.group(1))
                wx.PostEvent(self.monitor, ProgressChangedEvent(value=int(percent), total="", speed="", eta=""))

    def download(self):
        command = [
            paths.yt_dlp_path,
            "--no-check-certificate",
            "-o",
            f"{self.path}\\%(title)s.%(ext)s",
            "-f",
            self.downloading_format,
            "--progress",
            self.url
        ]
        if self.convert:
            command.extend(["-x", "--audio-format", "mp3", "--audio-quality", self.get_quality()])
        
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        
        for line in self.process.stdout:
            self.progress_parser(line)
        
        return self.process.wait()

def downloadAction(
    url, path, dlg, downloading_format, monitor, status_label, convert=False, folder=False
):
    downloader = Downloader(
        url, path, downloading_format, monitor, status_label, convert=convert, folder=folder
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
        status_label.SetString(4, "") # Clear the remaining amount string

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
