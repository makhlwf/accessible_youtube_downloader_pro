import requests
import wx
import utils
from language_handler import _
from wx.lib.newevent import NewEvent
import os
from paths import update_path
from threading import Thread
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlparse


ProgressChangedEvent, EVT_PROGRESS_CHANGED = NewEvent()
DownloadFinishedEvent, EVT_DOWNLOAD_FINISHED = NewEvent()


def _download_name_from_url(url):
    name = os.path.basename(unquote(urlparse(url).path))
    return name or "update.exe"


class UpdateDialog(wx.Dialog):
    def __init__(
        self, parent, url, dest=None, title=_("تنزيل التحديثات"), is_zip=False
    ):
        super().__init__(parent, title=title)
        self.dest = dest
        self.is_zip = is_zip
        self.download = True
        self.CentreOnParent()

        panel = wx.Panel(self)
        self.status = wx.TextCtrl(
            panel,
            -1,
            value=_("في انتظار بدء التحميل..."),
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL,
        )
        cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إيقاف التحميل"))
        self.progress = wx.Gauge(panel, -1, range=100)
        self.progress.Bind(EVT_PROGRESS_CHANGED, self.onChanged)
        self.Bind(EVT_DOWNLOAD_FINISHED, self.onFinished)
        cancelButton.Bind(wx.EVT_BUTTON, self.onCancel)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        Thread(target=self.updateDownload, args=[url], daemon=True).start()
        self.ShowModal()
        self.Destroy()

    def updateDownload(self, url):
        if self.dest is None:
            if os.path.exists(update_path):
                shutil.rmtree(update_path, ignore_errors=True)
            os.makedirs(update_path, exist_ok=True)
            name = os.path.join(update_path, _download_name_from_url(url))
        else:
            name = self.dest
            dest_dir = os.path.dirname(os.path.abspath(name))
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                if r.status_code != 200:
                    self.errorAction(download_path=name)
                    return
                size_str = r.headers.get("content-length")
                try:
                    size = int(size_str) if size_str else None
                except (ValueError, TypeError):
                    size = None
                recieved = 0
                progress = 0
                with open(name, "wb") as file:
                    for part in r.iter_content(1024 * 64):
                        if not part:
                            continue
                        file.write(part)
                        if not self.download:
                            self.cleanupDownload(name)
                            wx.CallAfter(self.EndModal, wx.ID_CANCEL)
                            return

                        recieved += len(part)
                        if size:
                            progress = int((recieved / size) * 100)
                            wx.PostEvent(
                                self.progress, ProgressChangedEvent(value=progress)
                            )
            wx.PostEvent(self.progress, ProgressChangedEvent(value=100))
            wx.PostEvent(self, DownloadFinishedEvent(path=name))
        except (OSError, requests.RequestException) as e:
            self.errorAction(e, download_path=name)

    def cleanupDownload(self, path=None):
        if self.dest is None:
            shutil.rmtree(update_path, ignore_errors=True)
            return
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def errorAction(self, exception=None, download_path=None):
        utils.show_error(
            _("لا يمكن اكمال التنزيل في الوقت الحالي"),
            exception,
            parent=self,
        )
        self.cleanupDownload(download_path)
        wx.CallAfter(self.EndModal, wx.ID_ERROR)

    def onChanged(self, event):
        self.progress.SetValue(event.value)
        self.status.SetValue(_("يتم الآن تنزيل الملف {}").format(event.value))

    def onFinished(self, event):
        if self.dest is not None:
            if self.is_zip:
                import zipfile

                try:
                    with zipfile.ZipFile(event.path, "r") as zip_ref:
                        zip_ref.extractall(os.path.dirname(event.path))
                    os.remove(event.path)
                except Exception as e:
                    utils.show_error(
                        _("حدث خطأ أثناء استخراج الملف"),
                        e,
                        self,
                    )
                    self.EndModal(wx.ID_ERROR)
                    return

            wx.MessageBox(_("اكتمل تنزيل الملف بنجاح"), _("نجاح"), parent=self)
            self.download = False
            self.EndModal(wx.ID_OK)
            return
        wx.MessageBox(
            _(
                "اكتمل تنزيل التحديث بنجاح. يرجى الضغط على موافق للشروع في عملية التثبيت"
            ),
            _("نجاح"),
            parent=self,
        )
        try:
            self.status.SetValue(_("جاري تثبيت التحديث"))
            path = os.path.abspath(event.path)
            self.launchInstaller(path)
        except Exception as e:
            utils.show_error(
                _(
                    "حدث خطأ ما عند محاولة فتح ملف التثبيت. فضلًا أعد محاولة التحديث مجددًا, أو تواصل مع المطور للإبلاغ بالمشكلة"
                ),
                e,
                self,
            )
            self.EndModal(wx.ID_ERROR)
            return
        self.download = False
        sys.exit()

    @staticmethod
    def launchInstaller(path):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        subprocess.Popen([path, "/SILENT"], cwd=os.path.dirname(path) or None)

    def onCancel(self, event):
        self.download = False

    def onClose(self, event):
        if self.download:
            message = wx.MessageBox(
                "هناك عملية تنزيل جارية. هل تريد إلغاءها؟",
                "إنهاء",
                style=wx.YES_NO,
                parent=self,
            )
            if message == wx.YES:
                self.download = False
            return
        self.EndModal(wx.ID_CANCEL)
