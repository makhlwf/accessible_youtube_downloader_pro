import os
import webbrowser

import wx

import application
import utils
from gui.activity_dialog import LoadingDialog
from gui.channel_dialog import ChannelDialog
from gui.download_progress import DownloadProgress
from gui.quality_selection import QualitySelectionDialog
from language_handler import _
from media_player.media_gui import MediaGui
from settings_handler import config_get
from theme_handler import apply_theme
from utils import get_audio_stream, get_video_stream
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import PlaylistResult


class PlaylistDialog(wx.Dialog):
    def __init__(self, parent, url):
        super().__init__(parent, title=application.name)
        self.CenterOnParent()
        self.url = url
        self.scraper = Scraper()
        self.Maximize(True)
        p = wx.Panel(self)
        l1 = wx.StaticText(p, -1, _("قائمة الفيديوهات: "))
        self.videosBox = wx.ListBox(p, -1)
        self.playButton = wx.Button(p, -1, _("تشغيل"), name="control")
        self.downloadButton = wx.Button(p, -1, _("تنزيل"), name="control")
        backButton = wx.Button(p, -1, _("رجوع"), name="control")
        self.contextSetup()

        hotkeys = wx.AcceleratorTable(
            [
                (0, wx.WXK_RETURN, self.audioPlayItemId),
                (wx.ACCEL_CTRL, wx.WXK_RETURN, self.videoPlayItemId),
                (wx.ACCEL_CTRL, ord("D"), self.directDownloadId),
                (wx.ACCEL_CTRL, ord("L"), self.copyItemId),
            ]
        )
        self.videosBox.SetAcceleratorTable(hotkeys)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(l1, 1)
        sizer.Add(self.videosBox, 1, wx.EXPAND)
        ctrlSizer = wx.BoxSizer(wx.HORIZONTAL)
        for control in p.GetChildren():
            if control.Name == "control":
                ctrlSizer.Add(control, 1)
        sizer.Add(ctrlSizer)
        p.SetSizer(sizer)
        self.playButton.Bind(wx.EVT_BUTTON, lambda e: self.playAudio())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.videosBox.Bind(wx.EVT_LISTBOX, self.onListBox)
        backButton.Bind(wx.EVT_BUTTON, lambda e: self.back())
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_CLOSE, lambda e: wx.Exit())
        apply_theme(self)
        try:
            # Instantiate PlaylistResult
            playlist_result_obj = PlaylistResult(self.url)
            # Call LoadingDialog with the async init_async method
            dialog = LoadingDialog(
                self.Parent, _("جاري عرض قائمة التشغيل"), playlist_result_obj.init_async
            )
            if dialog.error:
                raise dialog.error
            self.result = dialog.res

            if (
                self.result is None
            ):  # Handle case where init_async returns None due to error
                raise RuntimeError("Failed to initialize playlist")

            self.title = self.result.title
            self.SetTitle(f"{application.name} - {self.title}")
            self.videosBox.Set(
                self.result.get_display_titles() or [_("لا توجد فيديوهات متاحة")]
            )
            self.scraper.set_results(self.result)
            self.result.scraper = self.scraper
            for i in range(min(10, self.result.count)):
                self.scraper.add_item(i, priority=10)
        except Exception as e:  # Catch a broader exception here
            utils.show_error(
                _("حدث خطأ ما أثناء محاولة فتح قائمة التشغيل"),
                e,
                self,
            )
            self.Destroy()
            return
        self.Parent.Hide()
        self.Show()
        if self.result.count:
            self.videosBox.Selection = 0
        self.toggleChannelActions()

    def _download_media(
        self,
        format_type,
        url,
        dlg,
        download_type="video",
        path=None,
        title=None,
        quality=None,
    ):
        from download_handler.downloader import start_media_download

        folder = download_type != "video"
        start_media_download(
            url,
            format_type,
            self,
            path=path,
            title=title,
            quality=quality,
            folder=folder,
        )

    def contextSetup(self):
        self.contextMenu = wx.Menu()
        videoPlayItem = self.contextMenu.Append(-1, _("تشغيل"))
        self.videoPlayItemId = videoPlayItem.GetId()
        audioPlayItem = self.contextMenu.Append(-1, _("التشغيل كمقطع صوتي"))
        self.audioPlayItemId = audioPlayItem.GetId()

        self.downloadMenu = wx.Menu()
        videoSubMenu = wx.Menu()
        self.mp4ItemId = videoSubMenu.Append(-1, "mp4").GetId()
        self.mkvItemId = videoSubMenu.Append(-1, "mkv").GetId()
        self.downloadMenu.AppendSubMenu(videoSubMenu, _("فيديو"))

        audioSubMenu = wx.Menu()
        self.m4aItemId = audioSubMenu.Append(-1, "m4a").GetId()
        self.mp3ItemId = audioSubMenu.Append(-1, "mp3").GetId()
        self.wavItemId = audioSubMenu.Append(-1, "wav").GetId()
        self.flacItemId = audioSubMenu.Append(-1, "flac").GetId()
        self.downloadMenu.AppendSubMenu(audioSubMenu, _("صوت"))

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

        def popup():
            if self.result.videos:
                self.videosBox.PopupMenu(self.contextMenu)

        self.videosBox.Bind(wx.EVT_CONTEXT_MENU, lambda event: popup())
        # binding item events
        self.videosBox.Bind(
            wx.EVT_MENU, lambda e: self.playVideo(), id=self.videoPlayItemId
        )
        self.videosBox.Bind(
            wx.EVT_MENU, lambda e: self.playAudio(), id=self.audioPlayItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mp4"), id=self.mp4ItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mkv"), id=self.mkvItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onAudioDownload(e, "m4a"), id=self.m4aItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onAudioDownload(e, "mp3"), id=self.mp3ItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onAudioDownload(e, "wav"), id=self.wavItemId
        )
        self.Bind(
            wx.EVT_MENU, lambda e: self.onAudioDownload(e, "flac"), id=self.flacItemId
        )
        self.videosBox.Bind(
            wx.EVT_MENU, lambda e: self.directDownload(), id=self.directDownloadId
        )
        self.videosBox.Bind(wx.EVT_MENU, self.onCopy, id=self.copyItemId)
        self.videosBox.Bind(wx.EVT_MENU, self.onOpenChannel, openChannelInAppItem)
        self.videosBox.Bind(
            wx.EVT_MENU, self.onOpenChannelInBrowser, openChannelInBrowserItem
        )
        self.videosBox.Bind(wx.EVT_MENU, self.onDownloadChannel, downloadChannelItem)
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, webbrowserItem)

    def onOpenInBrowser(self, event):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        webbrowser.open(url)

    def onCopy(self, event):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        utils.copy_to_clipboard(url)
        wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def onOpenChannel(self, event):
        n = self.videosBox.Selection
        channel = self.result.videos[n]["channel"]
        if channel["url"]:
            ChannelDialog(self, channel["url"], channel["name"])

    def onOpenChannelInBrowser(self, event):
        n = self.videosBox.Selection
        channel = self.result.videos[n]["channel"]
        if channel["url"]:
            webbrowser.open(channel["url"])

    def onDownloadChannel(self, event):
        n = self.videosBox.Selection
        title = self.result.videos[n]["channel"]["name"]
        url = self.result.videos[n]["channel"]["url"]
        download_type = "channel"
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")),
            url,
            dlg,
            download_type,
            title=title,
        )

    def playVideo(self):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = self.result.get_title(n)
        if not utils.check_yt_dlp(self):
            return
        stream = self.result.get_stream(n, audio_mode=False)
        if stream is None:
            stream = LoadingDialog(self, _("جاري التشغيل"), get_video_stream, url).res
        gui = MediaGui(self, title, stream, url, True, self.result)
        gui.path = os.path.join(gui.path, utils.sanitize_filename(self.title))
        self.Hide()

    def playAudio(self):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = self.result.get_title(n)
        if not utils.check_yt_dlp(self):
            return
        stream = self.result.get_stream(n, audio_mode=True)
        if stream is None:
            stream = LoadingDialog(self, _("جاري التشغيل"), get_audio_stream, url).res
        gui = MediaGui(self, title, stream, url, audio_mode=True, results=self.result)
        gui.path = os.path.join(gui.path, utils.sanitize_filename(self.title))
        self.Hide()

    def onVideoDownload(self, event, format_type):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = self.result.get_title(n)

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
        dlg = DownloadProgress(self.Parent, title)
        self._download_media(
            format_type,
            url,
            dlg,
            "video",
            os.path.join(config_get("path"), utils.sanitize_filename(self.title)),
            quality=quality,
        )

    def directDownload(self):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = self.result.get_title(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")),
            url,
            dlg,
            "video",
            os.path.join(config_get("path"), utils.sanitize_filename(self.title)),
        )

    def onAudioDownload(self, event, format_type):
        n = self.videosBox.Selection
        video_id = self.result.get_id(n)
        url = f"https://www.youtube.com/watch?v={video_id}"
        title = self.result.get_title(n)
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            format_type,
            url,
            dlg,
            "video",
            os.path.join(config_get("path"), utils.sanitize_filename(self.title)),
        )

    def onListBox(self, event):
        n = self.videosBox.Selection
        self.toggleChannelActions()
        if n != wx.NOT_FOUND:
            self.scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.result.count)):
                    self.scraper.add_item(i, priority=10)

    def toggleChannelActions(self):
        n = self.videosBox.Selection
        enabled = (
            n != wx.NOT_FOUND
            and self.result.videos
            and n < len(self.result.videos)
            and bool(self.result.videos[n]["channel"].get("url"))
        )
        self.contextMenu.Enable(self.openChannelInAppItemId, enabled)
        self.contextMenu.Enable(self.openChannelInBrowserItemId, enabled)
        self.contextMenu.Enable(self.downloadChannelItemId, enabled)

    def onDownload(self, event):
        downloadMenu = wx.Menu()
        videoSubMenu = wx.Menu()
        mp4Id = videoSubMenu.Append(-1, "mp4").GetId()
        mkvId = videoSubMenu.Append(-1, "mkv").GetId()
        downloadMenu.AppendSubMenu(videoSubMenu, _("فيديو"))

        audioMenu = wx.Menu()
        m4aId = audioMenu.Append(-1, "m4a").GetId()
        mp3Id = audioMenu.Append(-1, "mp3").GetId()
        wavId = audioMenu.Append(-1, "wav").GetId()
        flacId = audioMenu.Append(-1, "flac").GetId()
        downloadMenu.AppendSubMenu(audioMenu, _("صوت"))

        self.Bind(wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mp4"), id=mp4Id)
        self.Bind(wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mkv"), id=mkvId)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "m4a"), id=m4aId)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "mp3"), id=mp3Id)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "wav"), id=wavId)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "flac"), id=flacId)

        self.PopupMenu(downloadMenu)
        self.videosBox.SetFocus()

    def back(self):
        self.Parent.Show()
        self.Destroy()

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE and not isinstance(
            self.FindFocus(), MediaGui
        ):
            self.back()
        else:
            event.Skip()
