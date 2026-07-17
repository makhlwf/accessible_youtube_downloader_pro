import os
import webbrowser
from threading import Thread

import pyperclip
import wx

import application
import utils
from download_handler.downloader import downloadAction
from gui.activity_dialog import LoadingDialog
from gui.download_progress import DownloadProgress
from gui.quality_selection import QualitySelectionDialog
from language_handler import _
from media_player.media_gui import MediaGui
from nvda_client.client import speak
from settings_handler import config_get
from theme_handler import apply_theme
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import CHANNEL_TABS, ChannelTabResult


class ChannelDialog(wx.Dialog):
    def __init__(self, parent, url, title=""):
        super().__init__(parent, title=application.name)
        self.url = url
        self.title = title or _("قناة")
        self.results_by_tab = {}
        self.current_result = None
        self.scraper = Scraper()

        self.CenterOnParent()
        self.Maximize(True)
        panel = wx.Panel(self)

        tabLabel = wx.StaticText(panel, -1, _("تبويب القناة: "))
        self.tabBox = wx.Choice(panel, -1, choices=[label for _, label in CHANNEL_TABS])
        self.tabBox.Selection = self._default_tab_selection()

        listLabel = wx.StaticText(panel, -1, _("العناصر: "))
        self.itemsBox = wx.ListBox(panel, -1)
        self.loadMoreButton = wx.Button(panel, -1, _("تحميل المزيد"))
        self.loadMoreButton.Enabled = False
        self.playButton = wx.Button(panel, -1, _("تشغيل"), name="control")
        self.downloadButton = wx.Button(panel, -1, _("تنزيل"), name="control")
        backButton = wx.Button(panel, -1, _("رجوع"), name="control")

        self.contextSetup()
        hotkeys = wx.AcceleratorTable(
            [
                (0, wx.WXK_RETURN, self.audioPlayItemId),
                (wx.ACCEL_CTRL, wx.WXK_RETURN, self.videoPlayItemId),
                (wx.ACCEL_CTRL, ord("D"), self.directDownloadId),
                (wx.ACCEL_CTRL, ord("L"), self.copyItemId),
            ]
        )
        self.itemsBox.SetAcceleratorTable(hotkeys)

        tabSizer = wx.BoxSizer(wx.HORIZONTAL)
        tabSizer.Add(tabLabel, 1, wx.ALL, 5)
        tabSizer.Add(self.tabBox, 2, wx.EXPAND | wx.ALL, 5)

        controlSizer = wx.BoxSizer(wx.HORIZONTAL)
        for control in panel.GetChildren():
            if control.Name == "control":
                controlSizer.Add(control, 1, wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(tabSizer, 0, wx.EXPAND)
        sizer.Add(listLabel, 0, wx.ALL, 5)
        sizer.Add(self.itemsBox, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.loadMoreButton, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.Add(controlSizer, 0, wx.EXPAND)
        panel.SetSizer(sizer)

        self.tabBox.Bind(wx.EVT_CHOICE, self.onTabChoice)
        self.itemsBox.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.playAudio())
        self.itemsBox.Bind(wx.EVT_LISTBOX, self.onListBox)
        self.loadMoreButton.Bind(wx.EVT_BUTTON, self.onLoadMore)
        self.playButton.Bind(wx.EVT_BUTTON, lambda event: self.playAudio())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        backButton.Bind(wx.EVT_BUTTON, lambda event: self.back())
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_CLOSE, lambda event: self.back())

        apply_theme(self)
        if not self.load_selected_tab():
            self.Destroy()
            return
        self.Parent.Hide()
        self.Show()

    def _default_tab_selection(self):
        for index, (tab, _label) in enumerate(CHANNEL_TABS):
            if tab == "videos":
                return index
        return 0

    def selected_tab(self):
        return CHANNEL_TABS[self.tabBox.Selection][0]

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

        openChannelMenu = wx.Menu()
        openChannelInAppItem = openChannelMenu.Append(-1, _("فتح داخل التطبيق"))
        self.openChannelInAppItemId = openChannelInAppItem.GetId()
        openChannelInBrowserItem = openChannelMenu.Append(-1, _("فتح في المتصفح"))
        self.openChannelInBrowserItemId = openChannelInBrowserItem.GetId()
        self.contextMenu.AppendSubMenu(openChannelMenu, _("الانتقال إلى القناة"))

        downloadChannelItem = self.contextMenu.Append(-1, _("تنزيل القناة"))
        self.downloadChannelItemId = downloadChannelItem.GetId()
        copyItem = self.contextMenu.Append(-1, _("نسخ رابط المقطع"))
        self.copyItemId = copyItem.GetId()
        webbrowserItem = self.contextMenu.Append(-1, _("الفتح من خلال متصفح الإنترنت"))
        self.browserItemId = webbrowserItem.GetId()

        def popup():
            if self.current_result and self.current_result.count:
                self.itemsBox.PopupMenu(self.contextMenu)

        self.itemsBox.Bind(wx.EVT_CONTEXT_MENU, lambda event: popup())
        self.itemsBox.Bind(
            wx.EVT_MENU, lambda event: self.playVideo(), id=self.videoPlayItemId
        )
        self.itemsBox.Bind(
            wx.EVT_MENU, lambda event: self.playAudio(), id=self.audioPlayItemId
        )
        self.itemsBox.Bind(
            wx.EVT_MENU, lambda event: self.directDownload(), id=self.directDownloadId
        )
        self.itemsBox.Bind(wx.EVT_MENU, self.onCopy, id=self.copyItemId)
        self.itemsBox.Bind(
            wx.EVT_MENU, self.onOpenChannelInApp, id=self.openChannelInAppItemId
        )
        self.itemsBox.Bind(
            wx.EVT_MENU, self.onOpenChannelInBrowser, id=self.openChannelInBrowserItemId
        )
        self.itemsBox.Bind(
            wx.EVT_MENU, self.onDownloadChannel, id=self.downloadChannelItemId
        )
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, id=self.browserItemId)
        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)

    def _download_media(
        self,
        option,
        url,
        dlg,
        download_type="video",
        path=config_get("path"),
        title=None,
        quality=None,
    ):
        if option == 0:
            if quality:
                fmt = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
            else:
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4"
        else:
            fmt = "bestaudio[ext=m4a]"
        convert = option == 2
        folder = download_type != "video"
        if folder and title:
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

    def load_selected_tab(self):
        tab = self.selected_tab()
        if tab in self.results_by_tab:
            self.set_result(self.results_by_tab[tab])
            return True

        if tab != "about" and not utils.check_yt_dlp(self):
            return False

        try:
            result = LoadingDialog(
                self,
                _("جاري تحميل القناة"),
                ChannelTabResult,
                self.url,
                tab,
                self.title,
            ).res
        except Exception as exc:
            utils.show_error(_("تعذر تحميل القناة"), exc, parent=self)
            return False

        self.results_by_tab[tab] = result
        self.title = result.title or self.title
        self.SetTitle(f"{application.name} - {self.title}")
        self.set_result(result)
        return True

    def set_result(self, result):
        self.current_result = result
        titles = result.get_display_titles()
        self.itemsBox.Set(titles or [_("لا توجد عناصر متاحة")])
        self.scraper.set_results(result)
        result.scraper = self.scraper
        if result.count:
            self.itemsBox.Selection = 0
            for index in range(min(10, result.count)):
                self.scraper.add_item(index, priority=10)
        self.loadMoreButton.Enabled = bool(result.has_more)
        self.toggleActions()
        self.itemsBox.SetFocus()

    def current_selection(self):
        if not self.current_result or not self.current_result.count:
            return wx.NOT_FOUND
        selection = self.itemsBox.Selection
        if selection == wx.NOT_FOUND or selection >= self.current_result.count:
            return wx.NOT_FOUND
        return selection

    def current_type(self):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return "none"
        return self.current_result.get_type(selection)

    def onTabChoice(self, event):
        self.load_selected_tab()

    def onListBox(self, event):
        self.toggleActions()
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        if self.current_result.get_type(selection) == "video":
            self.scraper.add_item(selection, priority=0)
        if (
            self.current_result.has_more
            and selection == self.current_result.count - 1
            and config_get("autoload")
        ):
            self.loadMore()

    def onLoadMore(self, event):
        self.loadMore()

    def loadMore(self):
        if not self.current_result or not self.current_result.has_more:
            return
        speak(_("جاري تحميل المزيد من النتائج"))

        def load():
            try:
                loaded = self.current_result.load_more()
                wx.CallAfter(self.onLoadMoreComplete, loaded)
            except Exception as exc:
                wx.CallAfter(utils.show_error, _("تعذر تحميل المزيد"), exc, self)

        Thread(target=load, daemon=True).start()

    def onLoadMoreComplete(self, loaded):
        if not loaded:
            speak(_("لا توجد عناصر إضافية"))
            self.loadMoreButton.Enabled = False
            return
        self.itemsBox.Append(self.current_result.get_last_titles())
        self.loadMoreButton.Enabled = bool(self.current_result.has_more)
        for index in range(
            self.current_result.count - self.current_result.new_videos,
            self.current_result.count,
        ):
            self.scraper.add_item(index, priority=10)
        speak(_("تم تحميل المزيد من نتائج البحث"))

    def open_selected(self):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        item_type = self.current_result.get_type(selection)
        if item_type == "playlist":
            from gui.playlist_dialog import PlaylistDialog

            PlaylistDialog(self, self.current_result.get_url(selection))
        elif item_type == "channel":
            ChannelDialog(
                self,
                self.current_result.get_url(selection),
                self.current_result.get_title(selection),
            )

    def playVideo(self):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        if self.current_result.get_type(selection) != "video":
            self.open_selected()
            return
        url = self.current_result.get_url(selection)
        title = self.current_result.get_title(selection)
        if not utils.check_yt_dlp(self):
            return
        stream = self.current_result.get_stream(selection, audio_mode=False)
        if stream is None:
            stream = LoadingDialog(
                self, _("جاري التشغيل"), utils.get_playable_stream, url, False
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        gui = MediaGui(self, title, stream, url, True, self.current_result)
        gui.path = os.path.join(gui.path, utils.sanitize_filename(self.title))
        self.Hide()

    def playAudio(self):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        if self.current_result.get_type(selection) != "video":
            self.open_selected()
            return
        url = self.current_result.get_url(selection)
        title = self.current_result.get_title(selection)
        if not utils.check_yt_dlp(self):
            return
        stream = self.current_result.get_stream(selection, audio_mode=True)
        if stream is None:
            stream = LoadingDialog(
                self, _("جاري التشغيل"), utils.get_playable_stream, url, True
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        gui = MediaGui(
            self,
            title,
            stream,
            url,
            True,
            self.current_result,
            audio_mode=True,
        )
        gui.path = os.path.join(gui.path, utils.sanitize_filename(self.title))
        self.Hide()

    def onVideoDownload(self, event):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        url = self.current_result.get_url(selection)
        title = self.current_result.get_title(selection)
        download_type = self.current_result.get_type(selection)
        if download_type != "video":
            self._download_current(0)
            return
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
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(0, url, dlg, download_type, title=title, quality=quality)

    def onM4aDownload(self, event):
        self._download_current(1)

    def onMp3Download(self, event):
        self._download_current(2)

    def directDownload(self):
        self._download_current(int(config_get("defaultformat")))

    def _download_current(self, option):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return
        url = self.current_result.get_url(selection)
        title = self.current_result.get_title(selection)
        download_type = self.current_result.get_type(selection)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(option, url, dlg, download_type, title=title)

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
        self.itemsBox.SetFocus()

    def onOpenChannelInApp(self, event):
        channel = self.current_channel()
        if channel and channel["url"]:
            ChannelDialog(self, channel["url"], channel["name"])

    def onOpenChannelInBrowser(self, event):
        channel = self.current_channel()
        if channel and channel["url"]:
            webbrowser.open(channel["url"])

    def onDownloadChannel(self, event):
        channel = self.current_channel()
        if not channel or not channel["url"]:
            return
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), channel["name"])
        self._download_media(
            int(config_get("defaultformat")),
            channel["url"],
            dlg,
            "channel",
            title=channel["name"],
        )

    def current_channel(self):
        selection = self.current_selection()
        if selection == wx.NOT_FOUND:
            return None
        return self.current_result.get_channel(selection)

    def onOpenInBrowser(self, event):
        selection = self.current_selection()
        if selection != wx.NOT_FOUND:
            webbrowser.open(self.current_result.get_url(selection))

    def onCopy(self, event):
        selection = self.current_selection()
        if selection != wx.NOT_FOUND:
            pyperclip.copy(self.current_result.get_url(selection))
            wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def toggleActions(self):
        selection = self.current_selection()
        has_selection = selection != wx.NOT_FOUND
        item_type = self.current_type()
        is_video = item_type == "video"
        is_collection = item_type in ("playlist", "channel")
        is_info = item_type == "info"
        can_download = has_selection and not is_info
        channel = self.current_channel() if has_selection else None
        has_channel = bool(channel and channel.get("url"))

        self.playButton.Label = _("فتح") if is_collection else _("تشغيل")
        self.playButton.Enabled = has_selection and not is_info
        self.downloadButton.Enabled = can_download
        self.loadMoreButton.Enabled = bool(
            self.current_result and self.current_result.has_more
        )
        self.contextMenu.Enable(self.videoPlayItemId, is_video)
        self.contextMenu.Enable(self.audioPlayItemId, is_video)
        self.contextMenu.Enable(self.downloadId, can_download)
        self.contextMenu.Enable(self.directDownloadId, can_download)
        self.contextMenu.Enable(self.copyItemId, has_selection)
        self.contextMenu.Enable(self.browserItemId, has_selection)
        self.contextMenu.Enable(self.openChannelInAppItemId, has_channel)
        self.contextMenu.Enable(self.openChannelInBrowserItemId, has_channel)
        self.contextMenu.Enable(self.downloadChannelItemId, has_channel)

    def back(self):
        self.Parent.Show()
        self.Destroy()

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.back()
        else:
            event.Skip()
