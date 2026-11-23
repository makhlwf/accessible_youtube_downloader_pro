import pyperclip
import wx

import paths
import utils
from database import DownloadQueue, QueuedDownload
from download_handler.downloader import DownloadCancelled, start_media_download
from language_handler import _
from settings_handler import config_get, config_set
from speech_client import speak
from theme_handler import apply_theme

_download_window = None


def queue_add_message(result):
    if result is None:
        return _("Unable to save the download queue.")
    if not result:
        return _("This download is already queued.")
    return _("Added to queue. Items queued: {count}.").format(
        count=len(DownloadQueue.get_all() or ())
    )


def show_download_window(parent, default_url="", focus_queue=False):
    global _download_window
    if not _download_window or _download_window.IsBeingDeleted():
        _download_window = DownloadDialog(parent, default_url)
    elif default_url:
        _download_window.videoLink.SetValue(default_url)
    _download_window._refresh_queue()
    _download_window.Show()
    _download_window.Raise()
    if focus_queue:
        _download_window.queue_list.SetFocus()
    else:
        _download_window.videoLink.SetFocus()


class DownloadDialog(wx.Frame):
    def __init__(self, parent, default_url=""):
        wx.Frame.__init__(self, parent=parent, title=_("تنزيل"))
        self.path = config_get("path")
        self.Centre()
        self.downloading = False
        self.queue = []
        self.queue_run = None
        self.panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self.panel, -1, _("رابط التنزيل: : "))
        self.videoLink = wx.TextCtrl(self.panel, -1, value=default_url)
        self.videoLink.SetName(lbl.GetLabel())
        self.downloadingFormat = wx.RadioBox(
            self.panel, -1, _("نوع المقطع"), choices=[_("صوت"), _("فيديو")]
        )
        lbl2 = wx.StaticText(self.panel, -1, _("صيغة المقطع"), name="convert")
        self.convertingFormat = wx.Choice(
            self.panel, -1, choices=["m4a", "mp3", "wav", "flac"], name="convert"
        )
        default_audio = int(config_get("defaultaudio"))
        if not (0 <= default_audio < self.convertingFormat.GetCount()):
            default_audio = 0
        self.convertingFormat.SetSelection(default_audio)
        self.downloadButton = wx.Button(self.panel, -1, _("تنزيل"))
        self.downloadButton.SetDefault()
        self.changePath = wx.Button(
            self.panel, -1, f"{_('مسار مجلد التنزيل: ')} {self.path}"
        )
        self.changePath.Bind(wx.EVT_BUTTON, self.onChangePath)
        self.add_to_queue = wx.Button(self.panel, label=_("&Add to queue"))
        self.queue_list = wx.ListBox(self.panel, name=_("Download queue"))
        self.remove_from_queue = wx.Button(self.panel, label=_("&Remove selected"))
        self.clear_queue = wx.Button(self.panel, label=_("&Clear queue"))
        self.download_queue = wx.Button(self.panel, label=_("Download &queue"))
        self.queue_status = wx.TextCtrl(
            self.panel, style=wx.TE_READONLY, name=_("Queue status")
        )
        sizer1.Add(lbl, 1)
        sizer1.Add(self.videoLink, 1, wx.EXPAND)
        sizer.Add(sizer1, 1, wx.EXPAND)
        sizer.Add(self.downloadingFormat, 1, wx.EXPAND)
        sizer2.Add(lbl2)
        sizer2.Add(self.convertingFormat, 1, wx.EXPAND)
        sizer.Add(sizer2, 1, wx.EXPAND)
        sizer.Add(self.downloadButton, 1, wx.EXPAND)
        sizer.Add(self.changePath, 1, wx.EXPAND)
        sizer.Add(self.add_to_queue, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(wx.StaticText(self.panel, label=_("Download queue")), 0, wx.LEFT, 5)
        sizer.Add(self.queue_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.remove_from_queue, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.clear_queue, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.download_queue, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.queue_status, 0, wx.EXPAND | wx.ALL, 5)
        self.panel.SetSizer(sizer)
        # event bindings
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.add_to_queue.Bind(wx.EVT_BUTTON, self.on_add_to_queue)
        self.remove_from_queue.Bind(wx.EVT_BUTTON, self.on_remove_from_queue)
        self.clear_queue.Bind(wx.EVT_BUTTON, self.on_clear_queue)
        self.download_queue.Bind(wx.EVT_BUTTON, self.on_download_queue)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ACTIVATE, self.onActivate)
        self.Bind(wx.EVT_RADIOBOX, self.onRadioBox)
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        apply_theme(self)
        self._refresh_queue()
        self.Fit()

    def onRadioBox(self, event):
        if self.downloadingFormat.GetSelection() == 0:
            self.convertingFormat.SetItems(["m4a", "mp3", "wav", "flac"])
            default_audio = int(config_get("defaultaudio"))
            if not (0 <= default_audio < self.convertingFormat.GetCount()):
                default_audio = 0
            self.convertingFormat.SetSelection(default_audio)
        else:
            self.convertingFormat.SetItems(["mp4", "mkv"])
            self.convertingFormat.SetSelection(0)

    # an event method to call the detect clipboard function when activating the window
    def onActivate(self, event):
        if event.GetActive():
            self._refresh_queue(self.queue_list.GetSelection())
            if not self.downloading:
                self.detectFromClipboard()
            else:
                self.downloading = False
        event.Skip()

    # changing path button action
    def onChangePath(self, event):
        path = wx.DirSelector(
            _("اختر مجلد التنزيل"),
            paths.get_default_download_dir(),
            parent=self,
        )  # folder select dialog
        if path == "":
            return
        self.changePath.SetLabel(
            f"{_('مسار مجلد التنزيل: ')} {path}"
        )  # editing the change path label to show the new path
        self.path = path

    # detect youtube links from the clipboard function
    def detectFromClipboard(self):
        clip_content = pyperclip.paste()  # get the clipboard content
        detected_url = utils.extract_supported_youtube_url(clip_content)
        if detected_url and not utils.is_supported_youtube_url(self.videoLink.Value):
            self.videoLink.SetValue(detected_url)

    def _get_download(self):
        url = self.videoLink.GetValue().strip()
        if url == "" or not utils.is_supported_youtube_url(url):
            message = _("يرجى إدخال رابط صحيح.")
            speak(message, interrupt=True)
            utils.show_error(message, parent=self)
            wx.CallAfter(self.videoLink.SetFocus)
            return None
        cases = ("list", "channel", "playlist", "/user/", "/c/", "/@", "RD", "mix")
        return QueuedDownload(
            url,
            self.convertingFormat.GetStringSelection(),
            self.path or paths.get_default_download_dir(),
            any(case in url for case in cases),
        )

    def _remember_audio_format(self):
        if self.downloadingFormat.GetSelection() == 0:
            config_set("defaultaudio", str(self.convertingFormat.GetSelection()))

    def onDownload(self, event):
        if self.queue_run is not None:
            return
        item = self._get_download()
        if item is None or not utils.check_yt_dlp(self):
            return
        self._remember_audio_format()
        started = start_media_download(
            item.url,
            item.format,
            self.GetParent(),
            path=item.path,
            folder=item.folder,
        )

        if started:
            self.downloading = True
            self.Destroy()

    def _refresh_queue(self, selection=0):
        stored_queue = DownloadQueue.get_all()
        if stored_queue is not None:
            self.queue = stored_queue
        self.queue_list.Set(
            [
                _("{title} ({format})").format(
                    title=item.title or item.url, format=item.format
                )
                for item in self.queue
            ]
        )
        if self.queue:
            self.queue_list.SetSelection(max(0, min(selection, len(self.queue) - 1)))
        idle = self.queue_run is None
        self.remove_from_queue.Enable(idle and bool(self.queue))
        self.clear_queue.Enable(idle and bool(self.queue))
        self.download_queue.Enable(idle and bool(self.queue))
        self.add_to_queue.Enable(idle)
        self.downloadButton.Enable(idle)

    def _announce_queue_status(self, message):
        self.queue_status.ChangeValue(message)
        speak(message, interrupt=True)

    def on_add_to_queue(self, event):
        if self.queue_run is not None:
            return
        item = self._get_download()
        if item is None:
            return
        self._remember_audio_format()
        result = DownloadQueue.add(item)
        self._refresh_queue(len(self.queue))
        if result:
            self.videoLink.SetValue("")
            self.videoLink.SetFocus()
        self._announce_queue_status(queue_add_message(result))

    def on_remove_from_queue(self, event):
        index = self.queue_list.GetSelection()
        if self.queue_run is not None or not 0 <= index < len(self.queue):
            return
        if not DownloadQueue.remove(self.queue[index].id):
            self._announce_queue_status(_("Unable to save the download queue."))
            return
        self._refresh_queue(index)
        (self.queue_list if self.queue else self.videoLink).SetFocus()
        self._announce_queue_status(
            _("Removed from queue. Items queued: {count}.").format(
                count=len(self.queue)
            )
        )

    def on_clear_queue(self, event):
        if self.queue_run is not None or not self.queue:
            return
        answer = wx.MessageBox(
            _("Remove all items from the download queue?"),
            _("Download queue"),
            style=wx.YES_NO | wx.NO_DEFAULT,
            parent=self,
        )
        if answer != wx.YES:
            return
        if not DownloadQueue.clear():
            self._announce_queue_status(_("Unable to save the download queue."))
            return
        self._refresh_queue()
        self.queue_list.SetFocus()
        self._announce_queue_status(_("Download queue cleared."))

    def on_download_queue(self, event):
        self._refresh_queue()
        if self.queue_run is not None or not self.queue or not utils.check_yt_dlp(self):
            return
        self.queue_run = iter(enumerate(self.queue.copy(), start=1))
        self.queue_total = len(self.queue)
        self.queue_downloaded = 0
        self._refresh_queue()
        self._start_next_download()

    def _start_next_download(self):
        entry = next(self.queue_run, None)
        if entry is None:
            self._finish_queue(_("Download queue finished."))
            return
        index, item = entry
        title = _("Queue item {index} of {total}").format(
            index=index, total=self.queue_total
        )
        self._announce_queue_status(title)

        def finished(result):
            if isinstance(result, DownloadCancelled):
                self._finish_queue(_("Download queue canceled."))
                return
            if result == 0:
                self.queue_downloaded += 1
                if not DownloadQueue.remove(item.id):
                    self._finish_queue(_("Unable to save the download queue."))
                    return
                self._refresh_queue()
            self._start_next_download()

        if not start_media_download(
            item.url,
            item.format,
            self,
            path=item.path,
            title=title if not item.folder else None,
            folder=item.folder,
            on_finished=finished,
        ):
            self._finish_queue(_("Download queue stopped."))

    def _finish_queue(self, status):
        self.queue_run = None
        self._refresh_queue()
        (self.queue_list if self.queue else self.videoLink).SetFocus()
        self._announce_queue_status(
            _("{status} Downloaded: {downloaded}. Still queued: {remaining}.").format(
                status=status,
                downloaded=self.queue_downloaded,
                remaining=len(self.queue),
            )
        )

    def on_close(self, event):
        if self.queue_run is not None and event.CanVeto():
            speak(
                _("Close the download progress window to cancel the queue."),
                interrupt=True,
            )
            event.Veto()
            return
        event.Skip()

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()
