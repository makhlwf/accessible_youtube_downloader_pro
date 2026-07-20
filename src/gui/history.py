import webbrowser
from threading import Thread

import pyperclip
import wx
from language_handler import _
from gui.download_progress import DownloadProgress
from gui.activity_dialog import LoadingDialog
from gui.quality_selection import QualitySelectionDialog

from media_player.media_gui import MediaGui
from nvda_client.client import speak
from settings_handler import config_get
import utils
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult
from download_handler.downloader import (
    downloadAction,
    get_audio_download_format,
    get_video_download_format,
)
from database import Favorite


class HistoryDialog(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent=parent, title=_("سجل المشاهدة"))
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.panel = wx.Panel(self)
        self.scraper = Scraper()
        lbl = wx.StaticText(self.panel, -1, _("الفيديوهات التي شاهدتها مؤخرًا: "))
        self.historyList = wx.ListBox(self.panel, -1)
        self.loadMoreButton = wx.Button(self.panel, -1, _("تحميل المزيد من السجل"))
        self.loadMoreButton.Hide()

        self.playButton = wx.Button(self.panel, -1, _("تشغيل (enter)"), name="controls")
        self.downloadButton = wx.Button(self.panel, -1, _("تنزيل"), name="controls")
        self.favCheck = wx.CheckBox(self.panel, -1, _("تفضيل الفيديو"))

        backButton = wx.Button(self.panel, -1, _("العودة إلى النافذة الرئيسية"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(backButton, 1, wx.ALL)

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        for control in self.panel.GetChildren():
            if control.Name == "controls":
                sizer2.Add(control, 1)

        sizer.Add(sizer1, 0, wx.EXPAND)
        sizer.Add(lbl, 0, wx.ALL, 5)
        sizer.Add(self.historyList, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.loadMoreButton, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.Add(sizer2, 0, wx.EXPAND | wx.ALL, 5)

        self.panel.SetSizer(sizer)
        self.contextSetup()

        results_shortcuts = wx.AcceleratorTable(
            [
                (0, wx.WXK_RETURN, self.audioPlayItemId),
                (wx.ACCEL_CTRL, wx.WXK_RETURN, self.videoPlayItemId),
            ]
        )
        self.historyList.SetAcceleratorTable(results_shortcuts)

        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        self.playButton.Bind(wx.EVT_BUTTON, lambda event: self.playAudio())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.favCheck.Bind(wx.EVT_CHECKBOX, self.onFavorite)
        backButton.Bind(wx.EVT_BUTTON, lambda event: self.backAction())

        self.Bind(
            wx.EVT_LISTBOX_DCLICK, lambda event: self.playAudio(), self.historyList
        )
        self.historyList.Bind(wx.EVT_LISTBOX, self.onListBox)
        self.Bind(wx.EVT_CLOSE, self.onClose)

        self.history_data = []
        self.continuation = None
        self.favorites = Favorite()

        self.load_history()
        self.Show()
        self.Parent.Hide()

    def load_history(self, load_more=False):
        if not load_more:
            self.historyList.Set([_("جاري تحميل السجل... يرجى الانتظار")])
            speak(_("جاري تحميل السجل..."))
        else:
            speak(_("جاري تحميل المزيد من السجل"))

        def _load():
            data = utils.get_watch_history(self.continuation if load_more else None)
            wx.CallAfter(self._update_history, data, load_more)

        Thread(target=_load, daemon=True).start()

    def _update_history(self, data, load_more=False):
        new_videos = data.get("videos", [])
        self.continuation = data.get("continuation")

        old_count = len(self.history_data)
        if load_more:
            self.history_data.extend(new_videos)
        else:
            self.history_data = new_videos
            self.historyList.Clear()

        self.history_results = SimpleResult(self.history_data)
        self.history_results.scraper = self.scraper
        self.scraper.set_results(self.history_results)

        titles = [f"{item['title']} - {item['author']}" for item in self.history_data]
        self.historyList.Set(titles)

        if self.continuation:
            self.loadMoreButton.Show()
        else:
            self.loadMoreButton.Hide()

        if not self.history_data:
            self.historyList.Set([_("لا يوجد سجل مشاهدة متاح")])

        self.Layout()
        self.historyList.SetFocus()
        if load_more:
            speak(_("تم تحميل المزيد من السجل"))
            for i in range(old_count, self.history_results.count):
                self.scraper.add_item(i, priority=10)
        else:
            speak(_("تم تحميل السجل"))
            for i in range(min(10, self.history_results.count)):
                self.scraper.add_item(i, priority=10)
        self.toggleFavorite()

    def onLoadMore(self, event):
        self.load_history(True)

    def playVideo(self, audio_mode=False):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            return
        video_data = self.history_data[selection]
        url = video_data["url"]
        title = video_data["title"]

        stream = self.history_results.get_stream(selection, audio_mode=audio_mode)
        if stream is None:
            if not utils.check_yt_dlp(self):
                return
            stream = LoadingDialog(
                self,
                _("جاري التشغيل"),
                utils.get_playable_stream,
                url,
                audio_mode,
            ).res

        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return

        MediaGui(
            self,
            title,
            stream,
            url,
            audio_mode=audio_mode,
            results=self.history_results,
        )
        self.Hide()

    def playAudio(self):
        self.playVideo(audio_mode=True)

    def onListBox(self, event):
        self.toggleFavorite()
        n = self.historyList.Selection
        if n != wx.NOT_FOUND:
            self.scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.history_results.count)):
                    self.scraper.add_item(i, priority=10)

    def backAction(self):
        self.Destroy()
        self.Parent.Show()

    def onClose(self, event):
        self.backAction()

    def contextSetup(self):
        self.contextMenu = wx.Menu()

        videoPlayItem = self.contextMenu.Append(-1, _("تشغيل"))
        self.videoPlayItemId = videoPlayItem.GetId()
        audioPlayItem = self.contextMenu.Append(-1, _("التشغيل كمقطع صوتي"))
        self.audioPlayItemId = audioPlayItem.GetId()

        self.downloadMenu = wx.Menu()
        videoItem = self.downloadMenu.Append(-1, _("فيديو"))
        audioMenu = wx.Menu()
        m4aItem = audioMenu.Append(-1, "m4a")
        mp3Item = audioMenu.Append(-1, "mp3")
        self.downloadMenu.AppendSubMenu(audioMenu, _("صوت"))
        self.downloadId = self.contextMenu.AppendSubMenu(
            self.downloadMenu, _("تنزيل")
        ).GetId()

        copyItem = self.contextMenu.Append(-1, _("نسخ رابط المقطع"))
        webbrowserItem = self.contextMenu.Append(-1, _("الفتح من خلال متصفح الإنترنت"))

        def popup():
            if self.historyList.Strings != [] and self.history_data:
                self.historyList.PopupMenu(self.contextMenu)

        self.historyList.Bind(
            wx.EVT_MENU, lambda event: self.playVideo(), id=self.videoPlayItemId
        )
        self.historyList.Bind(
            wx.EVT_MENU, lambda event: self.playAudio(), id=self.audioPlayItemId
        )

        self.Bind(wx.EVT_MENU, self.onCopy, copyItem)
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, webbrowserItem)
        self.historyList.Bind(wx.EVT_CONTEXT_MENU, lambda event: popup())

        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)

    def onOpenInBrowser(self, event):
        selection = self.historyList.GetSelection()
        if selection != wx.NOT_FOUND and self.history_data:
            webbrowser.open(self.history_data[selection]["url"])

    def onDownload(self, event):
        downloadMenu = wx.Menu()
        videoItem = downloadMenu.Append(-1, _("فيديو"))
        audioMenu = wx.Menu()
        m4aItem = audioMenu.Append(-1, "m4a")
        mp3Item = audioMenu.Append(-1, "mp3")
        downloadMenu.AppendSubMenu(audioMenu, _("صوت"))
        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)
        self.PopupMenu(downloadMenu)

    def _download_media(self, option, url, dlg, title, quality=None):
        if option == 0:
            format = get_video_download_format(quality)
        else:
            format = get_audio_download_format(convert=option == 2)
        convert = True if option == 2 else False
        downloadAction(
            url,
            config_get("path"),
            dlg,
            format,
            dlg.gaugeProgress,
            dlg.textProgress,
            convert,
            False,
        )

    def onM4aDownload(self, event):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            return
        url = self.history_data[selection]["url"]
        title = self.history_data[selection]["title"]
        dlg = DownloadProgress(self, title)
        self._download_media(1, url, dlg, title)

    def onMp3Download(self, event):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            return
        url = self.history_data[selection]["url"]
        title = self.history_data[selection]["title"]
        dlg = DownloadProgress(self, title)
        self._download_media(2, url, dlg, title)

    def onVideoDownload(self, event):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            return
        url = self.history_data[selection]["url"]
        title = self.history_data[selection]["title"]

        if not utils.check_yt_dlp(self):
            return
        qualities = LoadingDialog(
            self,
            _("جاري جلب الجودات المتاحة..."),
            utils.get_available_qualities,
            url,
        ).res
        quality = None
        if qualities:
            quality_dlg = QualitySelectionDialog(self, qualities)
            if quality_dlg.ShowModal() == wx.ID_OK:
                quality = quality_dlg.get_selected_quality()
            else:
                return
        dlg = DownloadProgress(self, title)
        self._download_media(0, url, dlg, title, quality=quality)

    def onCopy(self, event):
        selection = self.historyList.GetSelection()
        if selection != wx.NOT_FOUND and self.history_data:
            pyperclip.copy(self.history_data[selection]["url"])
            wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def onFavorite(self, event):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            return
        video_data = self.history_data[selection]
        url = video_data["url"]
        if self.favCheck.Value:
            title = video_data["title"]
            author = video_data["author"]
            display_title = f"{title}. {author}"
            # History data might not have channel URL, we can omit it or try to find it
            data = {
                "title": title,
                "display_title": display_title,
                "url": url,
                "live": 1 if video_data.get("is_live") else 0,
                "channel_url": "",  # We don't have this in history easily
                "channel_name": author,
            }
            self.favorites.add_favorite(data)
            speak(_("تمت إضافة الفيديو إلى قائمة المفضلة"))
        else:
            self.favorites.remove_favorite(url)
            speak(_("تم حذف الفيديو من قائمة المفضلة"))

    def toggleFavorite(self):
        selection = self.historyList.GetSelection()
        if selection == wx.NOT_FOUND or not self.history_data:
            self.favCheck.Disable()
            return
        self.favCheck.Enable()
        url = self.history_data[selection]["url"]

        def check_url(target_url):
            favorites = self.favorites.get_all()
            fav_urls = {f["url"] for f in favorites}
            found = target_url in fav_urls

            def update():
                if self:
                    self.favCheck.SetValue(found)

            wx.CallAfter(update)

        Thread(target=check_url, args=[url], daemon=True).start()
