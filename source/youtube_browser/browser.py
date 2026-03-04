import webbrowser
from threading import Thread
import os
import re
import queue
import logging

import pyperclip
import wx
from language_handler import _
from gui.download_progress import DownloadProgress
from gui.search_dialog import SearchDialog
from gui.settings_dialog import SettingsDialog
from gui.playlist_dialog import PlaylistDialog
from gui.activity_dialog import LoadingDialog

from media_player.media_gui import MediaGui
from nvda_client.client import speak
from settings_handler import config_get
from youtube_browser.search_handler import Search
from youtube_browser.scraper import Scraper
from utils import get_playable_stream
from async_utils import run_in_async_loop

from download_handler.downloader import downloadAction
from database import Favorite

logger = logging.getLogger(__name__)


class YoutubeBrowser(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent=parent, title=parent.Title)
        self.favorites = Favorite()
        self.scraper = Scraper()
        self.search = None

        self._init_ui()
        self._setup_menus()
        self._bind_events()

        if self.searchAction():
            self.Show()
            self.Parent.Hide()
            self.toggleFavorite()
        else:
            self.Destroy()

    def _init_ui(self):
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
        self.searchButton = searchButton  # Keep reference for accelerator
        backButton = wx.Button(self.panel, -1, _("العودة إلى النافذة الرئيسية"))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(backButton, 1, wx.ALL, 5)
        sizer1.Add(searchButton, 1, wx.ALL, 5)

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2.Add(self.playButton, 1, wx.ALL, 5)
        sizer2.Add(self.downloadButton, 1, wx.ALL, 5)
        sizer2.Add(self.favCheck, 1, wx.ALL, 5)

        sizer.Add(sizer1, 0, wx.EXPAND)
        sizer.Add(lbl, 0, wx.ALL, 5)
        sizer.Add(self.searchResults, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.loadMoreButton, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.Add(sizer2, 0, wx.EXPAND)

        self.panel.SetSizer(sizer)

        results_shortcuts = wx.AcceleratorTable(
            [
                (wx.ACCEL_NORMAL, wx.WXK_RETURN, 1001),
                (wx.ACCEL_CTRL, wx.WXK_RETURN, 1002),
            ]
        )
        self.searchResults.SetAcceleratorTable(results_shortcuts)

    def _setup_menus(self):
        menuBar = wx.MenuBar()
        optionsMenu = wx.Menu()
        settingsItem = optionsMenu.Append(-1, _("الإعدادات...\talt+s"))
        self.settingsItemId = settingsItem.GetId()

        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_ALT, ord("S"), self.settingsItemId),
                (wx.ACCEL_CTRL, ord("F"), self.searchButton.GetId()),
                (wx.ACCEL_CTRL, ord("D"), 1003),  # Direct download
                (wx.ACCEL_CTRL, ord("L"), 1004),  # Copy link
            ]
        )
        self.SetAcceleratorTable(hotKeys)
        menuBar.Append(optionsMenu, _("خيارات"))
        self.SetMenuBar(menuBar)

        # Context Menu
        self.contextMenu = wx.Menu()
        self.videoPlayItemId = self.contextMenu.Append(-1, _("تشغيل")).GetId()
        self.audioPlayItemId = self.contextMenu.Append(
            -1, _("التشغيل كمقطع صوتي")
        ).GetId()

        self.downloadMenu = wx.Menu()
        self.videoDownloadId = self.downloadMenu.Append(-1, _("فيديو")).GetId()
        audioSubMenu = wx.Menu()
        self.m4aDownloadId = audioSubMenu.Append(-1, "m4a").GetId()
        self.mp3DownloadId = audioSubMenu.Append(-1, "mp3").GetId()
        self.downloadMenu.AppendSubMenu(audioSubMenu, _("صوت"))

        self.downloadId = self.contextMenu.AppendSubMenu(
            self.downloadMenu, _("تنزيل")
        ).GetId()
        self.directDownloadId = self.contextMenu.Append(
            -1, _("التنزيل المباشر...\tctrl+d")
        ).GetId()

        self.openChannelId = self.contextMenu.Append(-1, _("الانتقال إلى القناة")).GetId()
        self.downloadChannelId = self.contextMenu.Append(
            -1, _("تنزيل القناة")
        ).GetId()
        self.copyItemId = self.contextMenu.Append(-1, _("نسخ رابط المقطع")).GetId()
        self.browserItemId = self.contextMenu.Append(
            -1, _("الفتح من خلال متصفح الإنترنت")
        ).GetId()

    def _bind_events(self):
        self.Bind(wx.EVT_MENU, self.onSettings, id=self.settingsItemId)
        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        self.playButton.Bind(wx.EVT_BUTTON, lambda e: self.playAudio())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.favCheck.Bind(wx.EVT_CHECKBOX, self.onFavorite)
        self.searchButton.Bind(wx.EVT_BUTTON, self.onSearch)
        self.Bind(wx.EVT_BUTTON, self.backAction)  # Assuming backButton is focused correctly

        self.searchResults.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.playAudio())
        self.searchResults.Bind(wx.EVT_LISTBOX, self.onListBox)
        self.searchResults.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)

        self.Bind(wx.EVT_MENU, lambda e: self.playAudio(), id=1001)
        self.Bind(wx.EVT_MENU, lambda e: self.playVideo(), id=1002)
        self.Bind(wx.EVT_MENU, lambda e: self.playVideo(), id=self.videoPlayItemId)
        self.Bind(wx.EVT_MENU, lambda e: self.playAudio(), id=self.audioPlayItemId)

        self.Bind(wx.EVT_MENU, self.onVideoDownload, id=self.videoDownloadId)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, id=self.m4aDownloadId)
        self.Bind(wx.EVT_MENU, self.onMp3Download, id=self.mp3DownloadId)
        self.Bind(wx.EVT_MENU, lambda e: self.directDownload(), id=1003)
        self.Bind(wx.EVT_MENU, lambda e: self.directDownload(), id=self.directDownloadId)
        self.Bind(wx.EVT_MENU, self.onCopy, id=1004)
        self.Bind(wx.EVT_MENU, self.onCopy, id=self.copyItemId)

        self.Bind(wx.EVT_MENU, self.onOpenChannel, id=self.openChannelId)
        self.Bind(wx.EVT_MENU, self.onDownloadChannel, id=self.downloadChannelId)
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, id=self.browserItemId)

        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, lambda e: wx.Exit())

    def onSettings(self, event):
        SettingsDialog(self)

    def onContextMenu(self, event):
        if self.searchResults.GetCount() > 0:
            self.searchResults.PopupMenu(self.contextMenu)

    def _download_media(
        self,
        option,
        url,
        dlg,
        download_type="video",
        path=config_get("path"),
        title=None,
    ):
        if option == 0:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4"
        else:
            fmt = "bestaudio[ext=m4a]"
        convert = True if option == 2 else False
        folder = False if download_type == "video" else True
        if download_type == "playlist" and title:
            path = os.path.join(path, utils.sanitize_filename(title))
        downloadAction(
            url,
            path,
            dlg,
            fmt,
            dlg.gaugeProgress,
            dlg.textProgress,
            convert,
            folder,
        )

    def searchAction(self, value=""):
        dialog = SearchDialog(self, value=value)
        query = dialog.query
        filter_val = dialog.filter
        if query is None:
            self.toggleControls()
            return False

        speak(_("جاري البحث..."))
        self.searchResults.Clear()
        self.toggleControls()

        def search_thread():
            search_obj = Search(query, filter_val)
            try:
                self.search = run_in_async_loop(search_obj.init_async())
                if self.search is None:
                    raise Exception("Search returned no results")
                wx.CallAfter(self.on_search_complete)
            except Exception as e:
                logger.error(f"Search failed: {e}")
                wx.CallAfter(
                    utils.show_error,
                    _(
                        "تعذر إجراء عملية البحث بسبب وجود خلل ما في الاتصال بالشبكة."
                    ),
                    e,
                )

        Thread(target=search_thread, daemon=True).start()
        return True

    def on_search_complete(self):
        titles = self.search.get_titles()
        self.searchResults.Set(titles)
        self.toggleControls()
        if self.searchResults.GetCount() > 0:
            self.searchResults.SetSelection(0)
        self.searchResults.SetFocus()
        self.toggleDownload()
        self.togglePlay()
        speak(_("اكتمل البحث"))

        # Clear queue and add new videos for scraping
        self.scraper.set_results(self.search)
        self.search.scraper = self.scraper
        for i in range(min(10, self.search.count)):
            self.scraper.add_item(i, priority=10)

    def onSearch(self, event):
        if self.search:
            self.searchAction(self.search.query)
        else:
            self.searchAction()

    def playVideo(self):
        number = self.searchResults.Selection
        if number == wx.NOT_FOUND:
            return
        if self.search.get_type(number) == "playlist":
            PlaylistDialog(self, self.search.get_url(number))
            return
        title = self.search.get_title(number)
        url = self.search.get_url(number)
        stream = self.search.get_stream(number)
        if stream is None:
            stream = LoadingDialog(
                self, _("جاري التشغيل"), get_playable_stream, url, False
            ).res
        if stream:
            MediaGui(
                self,
                title,
                stream,
                url,
                can_download=(self.search.get_views(number) is not None),
                results=self.search,
            )
            self.Hide()

    def playAudio(self):
        number = self.searchResults.Selection
        if number == wx.NOT_FOUND or self.search.get_type(number) == "playlist":
            return
        title = self.search.get_title(number)
        url = self.search.get_url(number)
        stream = LoadingDialog(
            self, _("جاري التشغيل"), get_playable_stream, url, True
        ).res
        if stream:
            MediaGui(
                self,
                title,
                stream,
                url,
                can_download=(self.search.get_views(number) is not None),
                results=self.search,
                audio_mode=True,
            )
            self.Hide()

    def onHook(self, event):
        if (
            event.KeyCode == wx.WXK_SPACE
            and self.search
            and self.searchResults.Selection != wx.NOT_FOUND
            and self.search.get_type(self.searchResults.Selection) == "video"
            and self.FindFocus() == self.searchResults
        ):
            self.favCheck.Value = not self.favCheck.Value
            self.onFavorite(None)
        elif event.KeyCode == wx.WXK_BACK and not isinstance(
            self.FindFocus(), MediaGui
        ):
            self.backAction(None)
        else:
            event.Skip()

    def onOpenChannel(self, event):
        n = self.searchResults.Selection
        if n != wx.NOT_FOUND:
            webbrowser.open(self.search.get_channel(n)["url"])

    def onDownloadChannel(self, event):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        channel = self.search.get_channel(n)
        title = channel["name"]
        url = channel["url"]
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")), url, dlg, "channel", title=title
        )

    def onOpenInBrowser(self, event):
        n = self.searchResults.Selection
        if n != wx.NOT_FOUND:
            webbrowser.open(self.search.get_url(n))

    def onDownload(self, event):
        downloadMenu = wx.Menu()
        vId = downloadMenu.Append(-1, _("فيديو")).GetId()
        audioMenu = wx.Menu()
        mId = audioMenu.Append(-1, "m4a").GetId()
        mpId = audioMenu.Append(-1, "mp3").GetId()
        downloadMenu.AppendSubMenu(audioMenu, _("صوت"))

        self.Bind(wx.EVT_MENU, self.onVideoDownload, id=vId)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, id=mId)
        self.Bind(wx.EVT_MENU, self.onMp3Download, id=mpId)
        self.PopupMenu(downloadMenu)

    def onM4aDownload(self, event):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        url = self.search.get_url(n)
        title = self.search.get_title(n)
        download_type = self.search.get_type(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(1, url, dlg, download_type, title=title)

    def onMp3Download(self, event):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        url = self.search.get_url(n)
        title = self.search.get_title(n)
        download_type = self.search.get_type(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(2, url, dlg, download_type, title=title)

    def onVideoDownload(self, event):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        url = self.search.get_url(n)
        title = self.search.get_title(n)
        download_type = self.search.get_type(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(0, url, dlg, download_type, title=title)

    def onCopy(self, event):
        n = self.searchResults.Selection
        if n != wx.NOT_FOUND:
            pyperclip.copy(self.search.get_url(n))
            wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def loadMore(self):
        if not self.search:
            return
        speak(_("جاري تحميل المزيد من النتائج"))

        def load_more_thread():
            try:
                result = run_in_async_loop(self.search.load_more())
                wx.CallAfter(self.on_load_more_complete, result)
            except Exception as e:
                logger.error(f"Load more failed: {e}")
                wx.CallAfter(
                    utils.show_error,
                    _(
                        "لم يتمكن البرنامج من تحميل المزيد من النتائج."
                    ),
                    e,
                )
                speak(_("لم يتمكن البرنامج من تحميل المزيد من النتائج"))

        Thread(target=load_more_thread, daemon=True).start()

    def on_load_more_complete(self, result):
        if not result:
            speak(_("لم يتمكن البرنامج من تحميل المزيد من النتائج"))
            return
        self.searchResults.Append(self.search.get_last_titles())
        for i in range(self.search.count - self.search.new_videos, self.search.count):
            self.scraper.add_item(i, priority=10)
        speak(_("تم تحميل المزيد من نتائج البحث"))
        self.searchResults.SetFocus()

    def onListBox(self, event):
        self.toggleDownload()
        self.togglePlay()
        self.toggleFavorite()
        n = self.searchResults.Selection
        if n != wx.NOT_FOUND:
            self.scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.search.count)):
                    self.scraper.add_item(i, priority=10)

        if self.searchResults.Selection == self.searchResults.GetCount() - 1:
            if not config_get("autoload"):
                self.loadMoreButton.Enabled = True
                return
            self.loadMore()
        else:
            self.loadMoreButton.Enabled = False

    def onLoadMore(self, event):
        self.loadMore()

    def backAction(self, event):
        self.Destroy()
        self.Parent.Show()

    def toggleControls(self):
        show = self.searchResults.GetCount() > 0
        for control in self.panel.GetChildren():
            if control.Name == "controls":
                control.Show(show)
        self.loadMoreButton.Show(show and not config_get("autoload"))
        self.panel.Layout()

    def toggleDownload(self):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        is_live = self.search.get_views(n) is None and self.search.get_type(n) == "video"
        enable = not is_live
        self.contextMenu.Enable(self.downloadId, enable)
        self.contextMenu.Enable(self.directDownloadId, enable)
        self.downloadButton.Enabled = enable

    def togglePlay(self):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        is_playlist = self.search.get_type(n) == "playlist"
        self.playButton.Label = _("فتح") if is_playlist else _("تشغيل (enter)")
        self.contextMenu.Enable(self.videoPlayItemId, not is_playlist)
        self.contextMenu.Enable(self.audioPlayItemId, not is_playlist)

    def onFavorite(self, event):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        url = self.search.get_url(n)
        if self.favCheck.Value:
            title = self.search.get_title(n)
            channel = self.search.get_channel(n)
            data = {
                "title": title,
                "display_title": f"{title}. {channel['name']}",
                "url": url,
                "live": 1 if not self.search.get_views(n) else 0,
                "channel_url": channel["url"],
                "channel_name": channel["name"],
            }
            self.favorites.add_favorite(data)
            speak(_("تمت إضافة الفيديو إلى قائمة المفضلة"))
        else:
            self.favorites.remove_favorite(url)
            speak(_("تم حذف الفيديو من قائمة المفضلة"))

    def toggleFavorite(self):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            self.favCheck.Enabled = False
            return
        self.favCheck.Enabled = self.search.get_type(n) == "video"
        if not self.favCheck.Enabled:
            return

        url = self.search.get_url(n)
        def check_url(target_url):
            favorites = self.favorites.get_all()
            fav_urls = {f["url"] for f in favorites}
            found = target_url in fav_urls
            def update():
                if self:
                    self.favCheck.SetValue(found)
            wx.CallAfter(update)

        Thread(target=check_url, args=[url], daemon=True).start()

    def directDownload(self):
        n = self.searchResults.Selection
        if n == wx.NOT_FOUND:
            return
        if self.search.get_views(n) is None and self.search.get_type(n) == "video":
            return
        url = self.search.get_url(n)
        title = self.search.get_title(n)
        download_type = self.search.get_type(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")), url, dlg, download_type, title=title
        )


    def onShow(self, event):
        self.searchResults.SetFocus()
        event.Skip()
