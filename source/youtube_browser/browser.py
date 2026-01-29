import webbrowser
from threading import Thread
import os
import re
import queue
import time

import pyperclip
import wx
from gui.download_progress import DownloadProgress
from gui.search_dialog import SearchDialog
from gui.settings_dialog import SettingsDialog
from gui.playlist_dialog import PlaylistDialog
from gui.activity_dialog import LoadingDialog

from media_player.media_gui import MediaGui
from nvda_client.client import speak
from settings_handler import config_get
from youtube_browser.search_handler import Search
from utiles import get_audio_stream, get_video_stream, get_playable_stream
from async_utils import run_in_async_loop

from download_handler.downloader import downloadAction
from database import Favorite


class YoutubeBrowser(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent=parent, title=parent.Title)
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.panel = wx.Panel(self)
        lbl = wx.StaticText(self.panel, -1, _("نتائج البحث: "))
        self.searchResults = wx.ListBox(self.panel, -1)
        self.loadMoreButton = wx.Button(self.panel, -1, _("تحميل المزيد من النتائج"))
        self.loadMoreButton.Enabled = False
        self.loadMoreButton.Show(not config_get("autoload"))
        self.playButton = wx.Button(self.panel, -1, _("تشغيل (enter)"), name="controls")
        self.downloadButton = wx.Button(self.panel, -1, _("تنزيل"), name="controls")
        self.favCheck = wx.CheckBox(self.panel, -1, _("تفضيل الفيديو"))
        searchButton = wx.Button(self.panel, -1, _("بحث... (ctrl+f)"))
        backButton = wx.Button(self.panel, -1, _("العودة إلى النافذة الرئيسية"))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(backButton, 1, wx.ALL)
        sizer1.Add(searchButton, 1, wx.ALL)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        for control in self.panel.GetChildren():
            if control.Name == "controls":
                sizer2.Add(control, 1)
        sizer.Add(sizer1, 1, wx.EXPAND)
        sizer.Add(lbl, 1, wx.ALL)
        sizer.Add(self.searchResults, 1, wx.EXPAND)
        sizer.Add(self.loadMoreButton, 1)
        sizer.Add(sizer2, 1)
        self.panel.SetSizer(sizer)
        self.contextSetup()
        results_shortcuts = wx.AcceleratorTable(
            [
                (0, wx.WXK_RETURN, self.audioPlayItemId),
                (wx.ACCEL_CTRL, wx.WXK_RETURN, self.videoPlayItemId),
            ]
        )
        self.searchResults.SetAcceleratorTable(results_shortcuts)
        menuBar = wx.MenuBar()
        optionsMenu = wx.Menu()
        settingsItem = optionsMenu.Append(-1, _("الإعدادات...\talt+s"))
        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_ALT, ord("S"), settingsItem.GetId()),
                (wx.ACCEL_CTRL, ord("F"), searchButton.GetId()),
                (wx.ACCEL_CTRL, ord("D"), self.directDownloadId),
                (wx.ACCEL_CTRL, ord("L"), self.copyItemId),
            ]
        )
        # hotkey table
        self.SetAcceleratorTable(hotKeys)
        menuBar.Append(optionsMenu, _("خيارات"))
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, lambda event: SettingsDialog(self), settingsItem)
        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        self.playButton.Bind(wx.EVT_BUTTON, lambda event: self.playVideo())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.favCheck.Bind(wx.EVT_CHECKBOX, self.onFavorite)
        searchButton.Bind(wx.EVT_BUTTON, self.onSearch)
        backButton.Bind(wx.EVT_BUTTON, lambda event: self.backAction())
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)

        self.Bind(
            wx.EVT_LISTBOX_DCLICK, lambda event: self.playVideo(), self.searchResults
        )
        self.searchResults.Bind(wx.EVT_LISTBOX, self.onListBox)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, lambda event: wx.Exit())
        if self.searchAction():
            self.Show()
            self.Parent.Hide()
        else:
            self.Destroy()
            return
        self.favorites = Favorite()
        self.togleFavorite()
        self.scraping_queue = queue.Queue()
        for i in range(15):
            Thread(target=self._scraper_worker, daemon=True).start()

    def sanitize_filename(self, filename):
        return re.sub(r'[<>:"/\\|?*]', '_', filename)

    def _add_result(self, title, search_obj, is_load_more=False):
        if self.search != search_obj:
            return
        self.searchResults.Append(title)
        if not is_load_more and self.searchResults.Count == 1:
            self.togleControls()
            self.togleDownload()
            self.toglePlay()
            if self.IsShown():
                self.searchResults.SetSelection(0)
                self.searchResults.SetFocus()

    def _on_task_finished(self, search_obj, task_type="search", result=True):
        if self.search != search_obj:
            return
        if not self.IsShown():
            return
            
        if task_type == "search":
            if self.search.count > 0:
                speak(_("اكتمل البحث"))
            else:
                speak(_("لم يتم العثور على نتائج"))
        elif task_type == "load_more":
            if result:
                speak(_("تم تحميل المزيد من نتائج البحث"))
                self.searchResults.SetFocus()
            else:
                speak(_("لم يتمكن البرنامج من تحميل المزيد من النتائج"))

    def searchAction(self, value=""):
        dialog = SearchDialog(self, value=value)
        query = dialog.query
        filter = dialog.filter
        if query is None:
            self.togleControls()
            return False

        speak(_("جاري البحث..."))
        self.searchResults.Clear()
        self.togleControls()

        def search_thread():
            search_obj_local = Search(query, filter)
            try:
                self.search = run_in_async_loop(search_obj_local.init_async())
                if self.search is None:
                    raise Exception
                
                raw_results = self.search.results
                raw_count = self.search.count
                self.search.results = {}
                self.search.count = 0
                
                for i in range(raw_count):
                    item = raw_results[i + 1]
                    if item["type"] == "video":
                        self.scraping_queue.put((self.search, item))
                
                for i in range(raw_count):
                    item = raw_results[i + 1]
                    if item["type"] == "video":
                        while not item.get("scraped") and self.search == search_obj_local:
                            time.sleep(0.05)
                    
                    if self.search != search_obj_local:
                        return
                        
                    if item.get("type") == "playlist" or item.get("stream"):
                        self.search.count += 1
                        self.search.results[self.search.count] = item
                        title = self.search.get_display_title(self.search.count - 1)
                        wx.CallAfter(self._add_result, title, search_obj_local)
                
                wx.CallAfter(self._on_task_finished, search_obj_local, "search")
            except Exception as e:
                print(e)
                wx.CallAfter(
                    wx.MessageBox,
                    _(
                        "تعذر إجراء عملية البحث بسبب وجود خلل ما في الاتصال بالشبكة.\nالتفاصيل: {}"
                    ).format(e),
                    _("خطأ"),
                    style=wx.ICON_ERROR,
                )

        Thread(target=search_thread).start()
        return True

    def onSearch(self, event):
        if hasattr(self, "search"):
            self.searchAction(self.search.query)
        else:
            self.searchAction()

    def playVideo(self):
        number = self.searchResults.Selection
        if self.search.get_type(number) == "playlist":
            PlaylistDialog(self, self.search.get_url(number))
            return
        title = self.search.get_title(number)
        url = self.search.get_url(number)
        print(url)
        stream = self.search.get_stream(number)
        if stream is None:
            stream = LoadingDialog(self, _("جاري التشغيل"), get_playable_stream, url).res
        gui = MediaGui(
            self,
            title,
            stream,
            url,
            True if self.search.get_views(number) is not None else False,
            results=self.search,
        )
        self.Hide()

    def playAudio(self):
        number = self.searchResults.Selection
        if self.search.get_type(number) == "playlist":
            return
        title = self.search.get_title(number)
        url = self.search.get_url(number)
        stream = self.search.get_stream(number)
        if stream is None:
            stream = LoadingDialog(self, _("جاري التشغيل"), get_playable_stream, url).res
        gui = MediaGui(
            self,
            title,
            stream,
            url,
            True if self.search.get_views(number) is not None else False,
            results=self.search,
            audio_mode=True,
        )
        self.Hide()

    def onHook(self, event):
        if (
            event.KeyCode == wx.WXK_SPACE
            and self.search.get_type(self.searchResults.Selection) == "video"
            and self.FindFocus() == self.searchResults
        ):
            self.favCheck.Value = not self.favCheck.Value
            self.onFavorite(None)
        elif event.KeyCode == wx.WXK_BACK and not type(self.FindFocus()) == MediaGui:
            self.backAction()
        else:
            event.Skip()

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
        directDownloadItem = self.contextMenu.Append(
            -1, _("التنزيل المباشر...\tctrl+d")
        )
        self.directDownloadId = directDownloadItem.GetId()
        openChannelItem = self.contextMenu.Append(-1, _("الانتقال إلى القناة"))
        downloadChannelItem = self.contextMenu.Append(-1, _("تنزيل القناة"))
        copyItem = self.contextMenu.Append(-1, _("نسخ رابط المقطع"))
        self.copyItemId = copyItem.GetId()
        webbrowserItem = self.contextMenu.Append(-1, _("الفتح من خلال متصفح الإنترنت"))

        def popup():
            if self.searchResults.Strings != []:
                self.searchResults.PopupMenu(self.contextMenu)

        self.searchResults.Bind(
            wx.EVT_MENU, lambda event: self.playVideo(), id=self.videoPlayItemId
        )
        self.searchResults.Bind(
            wx.EVT_MENU, lambda event: self.playAudio(), id=self.audioPlayItemId
        )
        self.searchResults.Bind(wx.EVT_MENU, self.onOpenChannel, openChannelItem)
        self.searchResults.Bind(
            wx.EVT_MENU, self.onDownloadChannel, downloadChannelItem
        )
        self.Bind(wx.EVT_MENU, self.onCopy, copyItem)
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, webbrowserItem)
        self.searchResults.Bind(wx.EVT_CONTEXT_MENU, lambda event: popup())
        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)
        self.Bind(wx.EVT_MENU, lambda event: self.directDownload(), directDownloadItem)

    def onOpenChannel(self, event):
        n = self.searchResults.Selection
        webbrowser.open(self.search.get_channel(n)["url"])

    def onDownloadChannel(self, event):
        n = self.searchResults.Selection
        channel = self.search.get_channel(n)
        title = channel["name"]
        url = channel["url"]
        download_type = "channel"
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")), url, dlg, download_type, title=title
        )

    def onOpenInBrowser(self, event):
        number = self.searchResults.Selection
        url = self.search.get_url(number)
        webbrowser.open(url)

    def onDownload(self, event):
        downloadMenu = wx.Menu()
        videoItem = downloadMenu.Append(-1, _("فيديو"))
        audioMenu = wx.Menu()
        m4aItem = audioMenu.Append(-1, "m4a")
        mp3Item = audioMenu.Append(-1, "mp3")
        downloadMenu.Append(-1, _("صوت"), audioMenu)
        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)
        self.PopupMenu(downloadMenu)

    def onM4aDownload(self, event):
        url = self.search.get_url(self.searchResults.Selection)
        title = self.search.get_title(self.searchResults.Selection)
        download_type = self.search.get_type(self.searchResults.Selection)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(1, url, dlg, download_type, title=title)

    def onMp3Download(self, event):
        url = self.search.get_url(self.searchResults.Selection)
        title = self.search.get_title(self.searchResults.Selection)
        download_type = self.search.get_type(self.searchResults.Selection)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(2, url, dlg, download_type, title=title)

    def onVideoDownload(self, event):
        url = self.search.get_url(self.searchResults.Selection)
        title = self.search.get_title(self.searchResults.Selection)
        download_type = self.search.get_type(self.searchResults.Selection)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(0, url, dlg, download_type, title=title)

    def onCopy(self, event):
        pyperclip.copy(self.search.get_url(self.searchResults.Selection))
        wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def loadMore(self):
        if self.searchResults.Strings == []:
            return
        speak(_("جاري تحميل المزيد من النتائج"))

        def load_more_thread():
            search_obj_local = self.search
            try:
                current_count = self.search.count
                load_more_result = run_in_async_loop(self.search.load_more())
                if not load_more_result:
                    wx.CallAfter(self._on_task_finished, search_obj_local, "load_more", False)
                    return

                new_items = []
                for i in range(current_count + 1, self.search.count + 1):
                    new_items.append(self.search.results[i])
                
                # Temporarily remove new items from Search to re-add them after scraping in order
                for i in range(current_count + 1, self.search.count + 1):
                    del self.search.results[i]
                self.search.count = current_count

                for item in new_items:
                    if item["type"] == "video":
                        self.scraping_queue.put((self.search, item))

                new_added = 0
                for item in new_items:
                    if item["type"] == "video":
                        while not item.get("scraped") and self.search == search_obj_local:
                            time.sleep(0.05)
                    
                    if self.search != search_obj_local:
                        return

                    if item.get("type") == "playlist" or item.get("stream"):
                        self.search.count += 1
                        self.search.results[self.search.count] = item
                        new_added += 1
                        title = self.search.get_display_title(self.search.count - 1)
                        wx.CallAfter(self._add_result, title, search_obj_local, is_load_more=True)

                self.search.new_videos = new_added
                wx.CallAfter(self._on_task_finished, search_obj_local, "load_more", True)
            except Exception as e:
                print(e)
                wx.CallAfter(
                    wx.MessageBox,
                    _(
                        "لم يتمكن البرنامج من تحميل المزيد من النتائج.\nالتفاصيل: {}"
                    ).format(e),
                    _("خطأ"),
                    style=wx.ICON_ERROR,
                )

        Thread(target=load_more_thread).start()

    def onListBox(self, event):
        self.togleDownload()
        self.toglePlay()
        self.togleFavorite()
        if self.searchResults.Selection == len(self.searchResults.Strings) - 1:
            if not config_get("autoload"):
                self.loadMoreButton.Enabled = True
                return
            Thread(target=self.loadMore).start()
        else:
            self.loadMoreButton.Enabled = False

    def onLoadMore(self, event):
        Thread(target=self.loadMore).start()

    def backAction(self):
        self.Destroy()
        self.Parent.Show()

    def togleControls(self):
        if self.searchResults.Strings == []:
            for control in self.panel.GetChildren():
                if control.Name == "controls":
                    control.Hide()
            self.loadMoreButton.Hide()
        else:
            for control in self.panel.GetChildren():
                if control.Name == "controls":
                    control.Show()
            self.loadMoreButton.Show(not config_get("autoload"))

    def togleDownload(self):
        n = self.searchResults.Selection
        if n == -1:
            return
        if self.search.get_views(n) is None and self.search.get_type(n) == "video":
            self.contextMenu.Enable(self.downloadId, False)
            self.contextMenu.Enable(self.directDownloadId, False)
            self.downloadButton.Enabled = False
            return
        self.contextMenu.Enable(self.downloadId, True)
        self.contextMenu.Enable(self.directDownloadId, True)
        self.downloadButton.Enabled = True

    def toglePlay(self):
        n = self.searchResults.Selection
        if n == -1:
            return
        contextMenuIds = (self.videoPlayItemId, self.audioPlayItemId)
        if self.search.get_type(n) == "playlist":
            self.playButton.Label = _("فتح")
            for i in contextMenuIds:
                self.contextMenu.Enable(i, False)
            return
            self.playButton.Enabled = True
            for i in contextMenuIds:
                self.contextMenu.Enable(i, True)

    def onFavorite(self, event):
        n = self.searchResults.Selection
        if n == -1:
            return
        url = self.search.get_url(n)
        if self.favCheck.Value:
            title = self.search.get_title(n)
            display_title = f"{title}. {self.search.get_channel(n)['name']}"
            channel_url = self.search.get_channel(n)["url"]
            channel_name = self.search.get_channel(n)["name"]
            live = 1 if not self.search.get_views(n) else 0
            data = {
                "title": title,
                "display_title": display_title,
                "url": url,
                "live": live,
                "channel_url": channel_url,
                "channel_name": channel_name,
            }
            self.favorites.add_favorite(data)
            speak(_("تمت إضافة الفيديو إلى قائمة المفضلة"))
        else:
            self.favorites.remove_favorite(url)
            speak(_("تم حذف الفيديو من قائمة المفضلة"))

    def togleFavorite(self):
        n = self.searchResults.Selection
        if n == -1:
            return
        self.favCheck.Enabled = self.search.get_type(n) == "video"
        if not self.favCheck.Enabled:
            return
        rows = self.favorites.get_all()
        url = self.search.get_url(n)

        def check_url(url):
            for row in rows:
                if url == row["url"]:
                    wx.CallAfter(self.favCheck.SetValue, True)
                    break
            else:
                wx.CallAfter(self.favCheck.SetValue, False)

        Thread(target=check_url, args=[url]).start()

    def directDownload(self):
        n = self.searchResults.Selection
        if self.search.get_views(n) is None and self.search.get_type(n) == "video":
            return
        url = self.search.get_url(self.searchResults.Selection)
        title = self.search.get_title(self.searchResults.Selection)
        download_type = self.search.get_type(self.searchResults.Selection)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")), url, dlg, download_type, title=title
        )

    def _scraper_worker(self):
        while True:
            item = self.scraping_queue.get()
            if item is None:
                break
            search_obj, item_data = item
            if search_obj == getattr(self, "search", None):
                if item_data.get("type") == "video" and item_data.get("stream") is None:
                    url = item_data.get("url")
                    try:
                        stream = get_playable_stream(url)
                        item_data["stream"] = stream
                    except:
                        pass
                item_data["scraped"] = True
            self.scraping_queue.task_done()

    def onShow(self, event):
        self.searchResults.SetFocus()
