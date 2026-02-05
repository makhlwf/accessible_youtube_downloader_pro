import requests
import wx
from language_handler import _
from wx.lib.newevent import NewEvent
import os
from paths import update_path
from threading import Thread
import shutil
import subprocess
import sys


ProgressChangedEvent, EVT_PROGRESS_CHANGED = NewEvent()
DownloadFinishedEvent, EVT_DOWNLOAD_FINISHED = NewEvent()


class UpdateDialog(wx.Dialog):
    def __init__(
        self, parent, url, dest=None, title=_("تنزيل التحديثات"), is_zip=False
    ):
        super().__init__(None, title=title)
        self.dest = dest
        self.is_zip = is_zip
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
        Thread(target=self.updateDownload, args=[url]).start()
        self.download = True
        self.ShowModal()
        self.Destroy()

    def updateDownload(self, url):
        if self.dest is None:
            if os.path.exists(update_path):
                shutil.rmtree(update_path)
            os.mkdir(update_path)
            name = os.path.join(update_path, url.split("/")[-1])
        else:
            name = self.dest
        try:
            with requests.get(url, stream=True) as r:
                if r.status_code != 200:
                    self.errorAction()
                    return
                size = r.headers.get("content-length")
                try:
                    size = int(size)
                except TypeError:
                    self.errorAction()
                    return
                recieved = 0
                progress = 0
                with open(name, "wb") as file:
                    for part in r.iter_content(1024):
                        file.write(part)
                        if not self.download:
                            file.close()
                            if self.dest is None:
                                shutil.rmtree(update_path)
                            else:
                                os.remove(self.dest)
                            self.EndModal(wx.ID_CANCEL)
                            return

                        recieved += len(part)
                        progress = int((recieved / size) * 100)
                        wx.PostEvent(
                            self.progress, ProgressChangedEvent(value=progress)
                        )
            wx.PostEvent(self, DownloadFinishedEvent(path=name))
        except requests.ConnectionError:
            self.errorAction()

    def errorAction(self):
        wx.MessageBox(
            _("لا يمكن اكمال التنزيل في الوقت الحالي"),
            _("خطأ"),
            style=wx.ICON_ERROR,
            parent=self,
        )
        if self.dest is None:
            shutil.rmtree(update_path)
        self.EndModal(wx.ID_ERROR)

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
                    wx.MessageBox(
                        _("حدث خطأ أثناء استخراج الملف: {}").format(str(e)),
                        _("خطأ"),
                        style=wx.ICON_ERROR,
                        parent=self,
                    )
                    self.EndModal(wx.ID_ERROR)
                    return

            wx.MessageBox(_("اكتمل تنزيل الملف بنجاح"), _("نجاح"), parent=self)
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
            self.status.Value = _("جاري تثبيت التحديث")
            path = os.path.join(update_path, event.path)
            subprocess.Popen('"{}" /silent'.format(path), shell=True)
        except Exception:
            wx.MessageBox(
                _(
                    "حدث خطأ ما عند محاولة فتح ملف التثبيت. فضلًا أعد محاولة التحديث مجددًا, أو تواصل مع المطور للإبلاغ بالمشكلة"
                ),
                _("خطأ"),
                style=wx.ICON_ERROR,
                parent=self,
            )
            self.EndModal(wx.ID_ERROR)
            return
        sys.exit()

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
