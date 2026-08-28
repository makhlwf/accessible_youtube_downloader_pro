import webbrowser

import wx

import application
import utils
from database import Favorite
from gui.activity_dialog import LoadingDialog
from gui.channel_dialog import ChannelDialog
from gui.download_progress import DownloadProgress
from gui.quality_selection import QualitySelectionDialog
from language_handler import _
from media_player.media_gui import MediaGui
from settings_handler import config_get
from speech_client import speak
from theme_handler import apply_theme


class Favorites(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title=application.name)
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        p = wx.Panel(self)
        l1 = wx.StaticText(p, -1, _("المفضلة: "))
        self.favList = wx.ListBox(p, -1)
        self.playButton = wx.Button(p, -1, _("تشغيل"), name="control")
        self.downloadButton = wx.Button(p, -1, _("تنزيل"), name="control")
        self.deleteButton = wx.Button(p, -1, _("إلغاء التفضيل"), name="control")
        backButton = wx.Button(p, -1, _("العودة إلى النافذة الرئيسية"), name="control")
        self.favorites = Favorite()
        self.rows = self.favorites.get_all()
        self.favList.Set([row["display_title"] for row in self.rows])
        if self.favList.Strings:
            self.favList.Selection = 0
            self.contextSetup()
            hotkeys = wx.AcceleratorTable(
                [
                    (0, wx.WXK_RETURN, self.audioPlayItemId),
                    (wx.ACCEL_CTRL, wx.WXK_RETURN, self.videoPlayItemId),
                    (wx.ACCEL_CTRL, ord("D"), self.directDownloadId),
                    (wx.ACCEL_CTRL, ord("L"), self.copyItemId),
                ]
            )
            self.favList.SetAcceleratorTable(hotkeys)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(l1, 1)
        sizer.Add(self.favList, 1, wx.EXPAND)
        ctrlSizer = wx.BoxSizer(wx.HORIZONTAL)
        for control in p.GetChildren():
            if control.Name == "control":
                ctrlSizer.Add(control, 1)
        sizer.Add(ctrlSizer)
        self.toggleControls()

        self.playButton.Bind(wx.EVT_BUTTON, lambda e: self.playAudio())
        self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
        backButton.Bind(wx.EVT_BUTTON, self.onBack)
        self.Bind(wx.EVT_CLOSE, lambda e: wx.Exit())
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        p.SetSizer(sizer)
        sizer.Fit(p)
        apply_theme(self)
        self.Show()

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

    def onDelete(self, event):
        n = self.favList.Selection
        if n == -1:
            return
        url = self.rows[n]["url"]
        self.favorites.remove_favorite(url)
        self.favList.Delete(n)
        self.rows.pop(n)
        self.toggleControls()
        try:
            self.favList.Selection = n
        except Exception:
            pass
        self.favList.SetFocus()
        speak(_("تم حذف الفيديو من قائمة المفضلة"))

    def playVideo(self):
        n = self.favList.Selection
        url = self.rows[n]["url"]
        title = self.rows[n]["title"]
        if not utils.check_yt_dlp(self):
            return
        stream = LoadingDialog(self, _("جاري التشغيل"), utils.get_video_stream, url).res
        MediaGui(
            self,
            title,
            stream,
            url,
            bool(not self.rows[n]["live"]),
            results=self.rows,
        )
        self.Hide()

    def playAudio(self):
        n = self.favList.Selection
        url = self.rows[n]["url"]
        title = self.rows[n]["title"]
        if not utils.check_yt_dlp(self):
            return
        stream = LoadingDialog(self, _("جاري التشغيل"), utils.get_audio_stream, url).res
        MediaGui(self, title, stream, url, audio_mode=True, results=self.rows)
        self.Hide()

    def toggleControls(self):
        for control in (self.playButton, self.downloadButton, self.deleteButton):
            if self.rows == []:
                control.Disable()

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
        openChannelInBrowserItem = openChannelMenu.Append(-1, _("فتح في المتصفح"))
        self.contextMenu.AppendSubMenu(openChannelMenu, _("الانتقال إلى القناة"))
        downloadChannelItem = self.contextMenu.Append(-1, _("تنزيل القناة"))
        copyItem = self.contextMenu.Append(-1, _("نسخ رابط المقطع"))
        self.copyItemId = copyItem.GetId()
        webbrowserItem = self.contextMenu.Append(-1, _("الفتح من خلال متصفح الإنترنت"))

        def popup():
            if self.rows != []:
                self.favList.PopupMenu(self.contextMenu)

        self.favList.Bind(wx.EVT_CONTEXT_MENU, lambda event: popup())
        self.favList.Bind(
            wx.EVT_MENU, lambda e: self.playVideo(), id=self.videoPlayItemId
        )
        self.favList.Bind(
            wx.EVT_MENU, lambda e: self.playAudio(), id=self.audioPlayItemId
        )
        self.favList.Bind(wx.EVT_MENU, self.onCopy, id=self.copyItemId)
        self.favList.Bind(
            wx.EVT_MENU, lambda e: self.directDownload(), id=self.directDownloadId
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

        self.favList.Bind(wx.EVT_MENU, self.onOpenChannel, openChannelInAppItem)
        self.favList.Bind(
            wx.EVT_MENU, self.onOpenChannelInBrowser, openChannelInBrowserItem
        )
        self.favList.Bind(wx.EVT_MENU, self.onDownloadChannel, downloadChannelItem)
        self.Bind(wx.EVT_MENU, self.onOpenInBrowser, webbrowserItem)

    def onOpenInBrowser(self, event):
        n = self.favList.Selection
        webbrowser.open(self.rows[n]["url"])

    def onOpenChannel(self, event):
        n = self.favList.Selection
        if self.rows[n]["channel_url"]:
            ChannelDialog(
                self,
                self.rows[n]["channel_url"],
                self.rows[n]["channel_name"],
            )

    def onOpenChannelInBrowser(self, event):
        n = self.favList.Selection
        if self.rows[n]["channel_url"]:
            webbrowser.open(self.rows[n]["channel_url"])

    def onDownloadChannel(self, event):
        n = self.favList.Selection
        title = self.rows[n]["channel_name"]
        url = self.rows[n]["channel_url"]
        download_type = "channel"
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")),
            url,
            dlg,
            download_type,
            title=title,
        )

    def onCopy(self, event):
        utils.copy_to_clipboard(self.rows[self.favList.Selection]["url"])
        wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def directDownload(self):
        n = self.favList.Selection

        url = self.rows[n]["url"]
        title = self.rows[n]["title"]
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(
            int(config_get("defaultformat")), url, dlg, "video", title=title
        )

    def onAudioDownload(self, event, format_type):
        n = self.favList.Selection
        url = self.rows[n]["url"]
        title = self.rows[n]["title"]
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), title)
        self._download_media(format_type, url, dlg, "video", title=title)

    def onVideoDownload(self, event, format_type):
        n = self.favList.Selection
        url = self.rows[n]["url"]
        title = self.rows[n]["title"]

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
        self._download_media(
            format_type, url, dlg, "video", title=title, quality=quality
        )

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

    def onHook(self, event):
        event.Skip()
        if (
            event.KeyCode in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE)
            and self.FindFocus() == self.favList
        ):
            self.onDelete(None)
        elif event.KeyCode == wx.WXK_BACK:
            self.onBack(None)

    def onBack(self, event):
        self.Parent.Show()
        self.Destroy()
