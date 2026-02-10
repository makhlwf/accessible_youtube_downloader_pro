import webbrowser
import pyperclip
import time
import wx
from language_handler import _
from gui.download_progress import DownloadProgress
from nvda_client.client import speak
from settings_handler import config_get, config_set
import application
import utils
from utils import get_playable_stream
from download_handler.downloader import downloadAction
from vlc import State
from gui.settings_dialog import SettingsDialog
from gui.description import DescriptionDialog
from gui.custom_controls import CustomButton
from py_yt import Video
from async_utils import run_in_async_loop
from threading import Thread
from database import Continue
from media_player.player import Player


def has_player(method):
    def wrapper(self, *args, **kwargs):
        if self.player is not None:
            return method(self, *args, **kwargs)
        return None

    return wrapper


class MediaGui(wx.Frame):
    def __init__(
        self,
        parent,
        title,
        stream,
        url,
        can_download=True,
        results=None,
        audio_mode=False,
    ):
        wx.Frame.__init__(self, parent, title=f"{title} - {application.name}")
        self.title = title
        self.stream = not can_download
        self.seek = int(config_get("seek"))
        self.results = results
        self.audio_mode = audio_mode
        self.current_quality = getattr(stream, "quality", None)
        self.path = config_get("path")
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.SetBackgroundColour(wx.BLACK)
        self.player = None
        self.url = url
        previousButton = CustomButton(self, -1, _("المقطع السابق"), name="controls")
        previousButton.Show() if self.results is not None else previousButton.Hide()
        beginingButton = CustomButton(self, -1, _("بداية المقطع"), name="controls")
        rewindButton = CustomButton(self, -1, _("إرجاع المقطع <"), name="controls")
        playButton = CustomButton(self, -1, _("تشغيل\إيقاف"), name="controls")
        forwardButton = CustomButton(self, -1, _("تقديم المقطع >"), name="controls")
        nextButton = CustomButton(self, -1, _("المقطع التالي"), name="controls")
        nextButton.Show() if self.results is not None else nextButton.Hide()
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        for control in self.GetChildren():
            if control.Name == "controls":
                sizer1.Add(control, 1)
        sizer.AddStretchSpacer()
        sizer.Add(sizer1)
        self.SetSizer(sizer)
        menuBar = wx.MenuBar()
        trackOptions = wx.Menu()
        downloadMenu = wx.Menu()
        videoItem = downloadMenu.Append(-1, _("فيديو"))
        audioMenu = wx.Menu()
        m4aItem = audioMenu.Append(-1, "m4a")
        mp3Item = audioMenu.Append(-1, "mp3")
        downloadMenu.AppendSubMenu(audioMenu, _("صوت"))
        downloadId = trackOptions.AppendSubMenu(downloadMenu, _("تنزيل")).GetId()
        trackOptions.Enable(downloadId, can_download)
        directDownloadItem = trackOptions.Append(-1, _("التنزيل المباشر...\tctrl+d"))
        directDownloadItem.Enable(can_download)
        self.qualityMenu = wx.Menu()
        self.qualityMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        self.qualitySubMenu = trackOptions.AppendSubMenu(
            self.qualityMenu, _("جودة التشغيل")
        )

        descriptionItem = trackOptions.Append(-1, _("وصف الفيديو\tctrl+shift+d"))
        copyItem = trackOptions.Append(-1, _("نسخ رابط المقطع\tctrl+l"))
        browserItem = trackOptions.Append(-1, _("الفتح من خلال متصفح الإنترنت\tctrl+b"))
        settingsItem = trackOptions.Append(-1, _("الإعدادات...\talt+s"))
        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("D"), directDownloadItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("D"), descriptionItem.GetId()),
                (wx.ACCEL_CTRL, ord("L"), copyItem.GetId()),
                (wx.ACCEL_CTRL, ord("B"), browserItem.GetId()),
                (wx.ACCEL_ALT, ord("S"), settingsItem.GetId()),
            ]
        )
        self.SetAcceleratorTable(hotKeys)
        menuBar.Append(trackOptions, _("خيارات المقطع"))
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, self.onVideoDownload, videoItem)
        self.Bind(wx.EVT_MENU, self.onM4aDownload, m4aItem)
        self.Bind(wx.EVT_MENU, self.onMp3Download, mp3Item)
        self.Bind(wx.EVT_MENU, self.onDirect, directDownloadItem)
        self.Bind(wx.EVT_MENU, self.onDescription, descriptionItem)
        self.Bind(wx.EVT_MENU, self.onCopy, copyItem)
        self.Bind(wx.EVT_MENU, self.onBrowser, browserItem)
        self.Bind(wx.EVT_MENU, lambda event: SettingsDialog(self), settingsItem)
        self.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
        self.prev_id = 100
        self.play_pause_id = 150
        self.next_id = 200
        self.registerHotKey()
        for hot_id in [self.prev_id, self.play_pause_id, self.next_id]:
            self.Bind(wx.EVT_HOTKEY, self.onHot, id=hot_id)
        for control in self.GetChildren():
            control.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
        previousButton.Bind(wx.EVT_BUTTON, lambda event: self.previous())
        beginingButton.Bind(wx.EVT_BUTTON, lambda event: self.beginingAction())
        rewindButton.Bind(wx.EVT_BUTTON, lambda event: self.rewindAction())
        playButton.Bind(wx.EVT_BUTTON, lambda event: self.playAction())
        forwardButton.Bind(wx.EVT_BUTTON, lambda event: self.forwardAction())
        nextButton.Bind(wx.EVT_BUTTON, lambda event: self.next())
        self.Bind(wx.EVT_CLOSE, lambda event: self.closeAction())
        self.Show()
        if stream is None:
            wx.MessageBox(
                _("لا يمكن تشغيل الرابط"), _("خطأ"), style=wx.ICON_ERROR, parent=self
            )
            self.closeAction()
            return
        options = []
        ua = None
        if hasattr(stream, "headers") and stream.headers:
            ua = stream.headers.get("User-Agent")
            if ua:
                options.append(f":http-user-agent={ua}")
        if hasattr(stream, "audio_url") and stream.audio_url:
            options.append(f":input-slave={stream.audio_url}")
        if audio_mode:
            options.append(":no-video")

        self.player = Player(
            stream.url,
            self.GetHandle() if not audio_mode else None,
            self,
            options=options,
        )
        if not audio_mode:
            Thread(target=self.fetch_qualities, daemon=True).start()
        if self.url in Continue.get_all() and config_get("continue"):
            self.player.media.set_position(Continue.get_all()[url])
        Thread(target=self.extract_description).start()
        self.history_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_history_timer, self.history_timer)
        self.history_timer.Start(10000)  # 10 seconds
        try:
            Thread(
                target=utils.update_watch_history,
                args=(
                    self.url,
                    self.player.media.get_time() / 1000
                    if self.player.media.get_time() != -1
                    else 0,
                ),
                daemon=True,
            ).start()
        except Exception:
            pass

    def on_history_timer(self, event):
        try:
            if self.player and self.player.media.get_state() == State.Playing:
                watched_seconds = self.player.media.get_time() / 1000
                if watched_seconds > 0:
                    Thread(
                        target=utils.update_watch_history,
                        args=(self.url, watched_seconds),
                        daemon=True,
                    ).start()
        except Exception:
            pass

    def fetch_qualities(self):
        qualities = utils.get_available_qualities(self.url, audio_mode=self.audio_mode)
        wx.CallAfter(self.populate_quality_menu, qualities)

    def populate_quality_menu(self, qualities):
        # Clear existing items
        for item in self.qualityMenu.GetMenuItems():
            self.qualityMenu.DestroyItem(item)

        if not qualities:
            self.qualityMenu.Append(-1, _("لا توجد جودات متاحة")).Enable(False)
            return

        for q in qualities:
            label = f"{q}kbps" if self.audio_mode else f"{q}p"
            item = self.qualityMenu.AppendCheckItem(-1, label)
            if q == self.current_quality:
                item.Check(True)
            self.Bind(wx.EVT_MENU, lambda event, h=q: self.on_change_quality(h), item)

    def on_change_quality(self, height):
        label = f"{height}kbps" if self.audio_mode else f"{height}p"
        speak(_("جاري تغيير الجودة إلى {}").format(label))
        position = self.player.media.get_position()

        def reload():
            self.player.media.stop()
            time.sleep(0.5)
            new_stream = utils.get_specific_quality_stream(
                self.url, height, audio_mode=self.audio_mode
            )
            if new_stream:
                self.current_quality = height

                def update_player():
                    options = []
                    if hasattr(new_stream, "headers") and new_stream.headers:
                        ua = new_stream.headers.get("User-Agent")
                        if ua:
                            options.append(f":http-user-agent={ua}")
                    if hasattr(new_stream, "audio_url") and new_stream.audio_url:
                        options.append(f":input-slave={new_stream.audio_url}")
                    if self.audio_mode:
                        options.append(":no-video")
                    self.player.set_media(new_stream.url, options)
                    self.player.media.play()
                    self.player.media.set_position(position)

                wx.CallAfter(update_player)
            else:
                speak(_("تعذر تغيير الجودة"))
                wx.CallAfter(self.player.media.play)

        Thread(target=reload, daemon=True).start()

    def _download_media(self, option, url, dlg, path=None):
        if path is None:
            path = self.path
        if option == 0:
            format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4"
        else:
            format = "bestaudio[ext=m4a]"
        convert = True if option == 2 else False
        folder = False  # Not relevant for single video downloads in MediaGui
        downloadAction(
            url,
            path,
            dlg,
            format,
            dlg.gaugeProgress,
            dlg.textProgress,
            convert,
            folder,
        )

    def playAction(self):
        state = self.player.media.get_state()
        if state in (State.NothingSpecial, State.Stopped):
            self.player.media.play()
        elif state in (State.Playing, State.Paused):
            if not self.stream:
                self.player.media.pause()
            else:
                self.player.media.stop()

    has_player

    @has_player
    def forwardAction(self):
        position = self.player.media.get_position()
        self.player.media.set_position(position + self.player.seek(self.seek))

    @has_player
    def rewindAction(self):
        position = self.player.media.get_position()
        self.player.media.set_position(position - self.player.seek(self.seek))

    def set_position(self, key):
        step = int(chr(key)) / 10
        self.player.media.set_position(step)
        speak(_("الوقت المنقضي: {}").format(self.player.get_elapsed()))

    @has_player
    def beginingAction(self):
        self.player.media.set_position(0.0)
        speak(_("بداية المقطع"))
        if self.player.media.get_state() in (State.NothingSpecial, State.Stopped):
            self.player.media.play()

    def closeAction(self):
        if hasattr(self, "history_timer"):
            self.history_timer.Stop()
        if self.player is not None:
            if (
                self.player.media.get_position() in (0.0, -1)
                and self.url in Continue.get_all()
            ):
                Continue.remove_continue(self.url)
            elif self.url in Continue.get_all():
                Continue.update(self.url, self.player.media.get_position())
            else:
                Continue.new_continue(self.url, self.player.media.get_position())

            # Final history update
            try:
                watched_seconds = self.player.media.get_time() / 1000
                if watched_seconds > 0:
                    Thread(
                        target=utils.update_watch_history,
                        args=(self.url, watched_seconds),
                        daemon=True,
                    ).start()
            except Exception:
                pass

            self.player.media.stop()
        self.GetParent().Show()

        self.Destroy()

    def registerHotKey(self):
        self.RegisterHotKey(self.prev_id, 0, wx.WXK_MEDIA_PREV_TRACK)
        self.RegisterHotKey(self.play_pause_id, 0, wx.WXK_MEDIA_PLAY_PAUSE)
        self.RegisterHotKey(self.next_id, 0, wx.WXK_MEDIA_NEXT_TRACK)

    def onHot(self, event):
        if event.Id == self.prev_id:
            self.previous()
        elif event.Id == self.play_pause_id:
            self.playAction()
        elif event.Id == self.next_id:
            self.next()

    def onKeyDown(self, event):
        event.Skip()
        if event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_PAUSE):
            self.playAction()
        elif event.GetKeyCode() == wx.WXK_RIGHT and not event.HasAnyModifiers():
            self.forwardAction()
        elif event.GetKeyCode() == wx.WXK_LEFT and not event.HasAnyModifiers():
            self.rewindAction()
        elif event.controlDown and event.KeyCode == wx.WXK_RIGHT:
            self.next()
        elif event.controlDown and event.KeyCode == wx.WXK_LEFT:
            self.previous()
        elif event.GetKeyCode() == wx.WXK_UP:
            self.increase_volume()
        elif event.GetKeyCode() == wx.WXK_DOWN:
            self.decrease_volume()
        elif event.GetKeyCode() == wx.WXK_HOME:
            self.beginingAction()
        elif event.KeyCode in range(49, 58):
            self.set_position(event.KeyCode)
        elif event.controlDown and event.shiftDown and event.KeyCode == ord("L"):
            self.get_duration()
        elif event.controlDown and event.shiftDown and event.KeyCode == ord("T"):
            if self.player is not None:
                speak(_("الوقت المنقضي: {}").format(self.player.get_elapsed()))
        elif event.KeyCode == ord("S"):
            if self.player is not None:
                self.player.media.set_rate(1.4)
                speak(_("سريع"))

        elif event.KeyCode == ord("D"):
            if self.player is not None:
                self.player.media.set_rate(1.0)

                speak(_("معتدل"))

        elif event.KeyCode == ord("F"):
            if self.player is not None:
                self.player.media.set_rate(0.6)

                speak(_("بطيء"))

        elif event.GetKeyCode() in (ord("-"), wx.WXK_NUMPAD_SUBTRACT):
            self.seek -= 1

            if self.seek < 1:
                self.seek = 1

            speak("{} {} {}".format(_("تحريك المقطع"), self.seek, _("ثانية/ثواني")))

            config_set("seek", self.seek)

        elif event.GetKeyCode() in (ord("="), wx.WXK_NUMPAD_ADD):
            self.seek += 1

            if self.seek > 10:
                self.seek = 10

            speak("{} {} {}".format(_("تحريك المقطع"), self.seek, _("ثانية/ثواني")))

            config_set("seek", self.seek)

        elif event.KeyCode == ord("R") and event.controlDown:
            if config_get("repeatTracks"):
                config_set("repeatTracks", False)

                speak(_("التكرار متوقف"))
            else:
                config_set("repeatTracks", True)

                speak(_("التكرار مفعل"))
                config_set("autonext", False)

        elif event.KeyCode == ord("R"):
            if self.player is not None:
                speak(_("المتبقي: {}").format(self.player.get_remaining()))

        elif event.KeyCode == ord("E"):
            if self.player is not None:
                speak(_("المنقضي: {}").format(self.player.get_elapsed()))

        elif event.KeyCode == ord("T"):
            if self.player is not None:
                speak(_("الإجمالي: {}").format(self.player.get_duration()))

        elif event.KeyCode == ord("P"):
            if self.player is not None:
                speak(_("{} بالمائة").format(self.player.get_position_percentage()))

        elif event.KeyCode == ord("N"):
            if config_get("autonext"):
                config_set("autonext", False)

                speak(_("تشغيل المقطع التالي تلقائيًا متوقف"))
            else:
                config_set("autonext", True)

                speak(_("تشغيل المقطع التالي تلقائيًا مفعل"))
                config_set("repeatTracks", False)

        elif event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.toggleFullScreen()

        elif event.GetKeyCode() == wx.WXK_ALT:
            if self.IsFullScreen():
                self.ShowFullScreen(False)

        elif event.GetKeyCode() == wx.WXK_ESCAPE:
            self.closeAction()

    @has_player
    def get_duration(self):
        speak(_("المدة: {}").format(self.player.get_duration()))

    @has_player
    def increase_volume(self):
        self.player.volume = self.player.volume + 5 if self.player.volume < 350 else 350
        self.player.media.audio_set_volume(self.player.volume)
        speak(f"{self.player.volume}%")
        config_set("volume", self.player.volume)

    @has_player
    def decrease_volume(self):
        self.player.volume = self.player.volume - 5 if self.player.volume > 0 else 0
        self.player.media.audio_set_volume(self.player.volume)
        speak(f"{self.player.volume}%")
        config_set("volume", self.player.volume)

    def toggleFullScreen(self):
        self.ShowFullScreen(not self.IsFullScreen())
        if self.IsFullScreen():
            speak(_("وضع ملء الشاشة مفعل"))
        else:
            speak(_("وضع ملء الشاشة متوقف"))

    def changeTrack(self, index):
        if hasattr(self.results, "scraper"):
            self.results.scraper.add_item(index, priority=0)
        if not isinstance(self.results, list):
            url = self.results.get_url(index)
            title = self.results.get_title(index)
        else:
            url = self.results[index]["url"]
            title = self.results[index]["title"]
        self.player.media.stop()
        if hasattr(self, "description"):
            del self.description
        try:
            stream = (
                self.results.get_stream(index)
                if hasattr(self.results, "get_stream")
                else None
            )
            if stream is None:
                stream = get_playable_stream(url, audio_mode=self.audio_mode)
        except Exception:
            return

        options = []
        if hasattr(stream, "headers") and stream.headers:
            ua = stream.headers.get("User-Agent")
            if ua:
                options.append(f":http-user-agent={ua}")
        if hasattr(stream, "audio_url") and stream.audio_url:
            options.append(f":input-slave={stream.audio_url}")
        if self.audio_mode:
            options.append(":no-video")

        self.player.set_media(stream.url, options=options)
        self.url = url
        self.title = title
        wx.CallAfter(self.SetTitle, f"{title} - {application.name}")
        self.player.media.play()
        self.player.media.audio_set_volume(self.player.volume)
        Thread(target=self.extract_description).start()
        if not self.audio_mode:
            for item in self.qualityMenu.GetMenuItems():
                self.qualityMenu.DestroyItem(item)
            self.qualityMenu.Append(-1, _("جاري التحميل...")).Enable(False)
            Thread(target=self.fetch_qualities, daemon=True).start()
        # Report new track to history
        try:
            Thread(
                target=utils.update_watch_history, args=(self.url, 0), daemon=True
            ).start()
        except Exception:
            pass

    def next(self):
        if self.results is None:
            return
        if hasattr(self.Parent, "searchResults"):
            self.Parent.searchResults.Selection += 1
            index = self.Parent.searchResults.Selection
        elif hasattr(self.Parent, "videosBox"):
            self.Parent.videosBox.Selection += 1
            index = self.Parent.videosBox.Selection
        elif hasattr(self.Parent, "home_feed_list"):
            self.Parent.home_feed_list.Selection += 1
            index = self.Parent.home_feed_list.Selection
        elif hasattr(self.Parent, "historyList"):
            self.Parent.historyList.Selection += 1
            index = self.Parent.historyList.Selection
        else:
            self.Parent.favList.Selection += 1
            index = self.Parent.favList.Selection
            if index < len(self.results):
                self.changeTrack(index)
            return
        self.changeTrack(index)
        if index >= self.results.count - 2:

            def load_more():
                if hasattr(self.Parent, "searchResults"):
                    if self.results.load_more():
                        wx.CallAfter(
                            self.Parent.searchResults.Append,
                            self.results.get_last_titles(),
                        )
                else:
                    if self.results.next():
                        wx.CallAfter(
                            self.Parent.videosBox.Append, self.results.get_new_titles()
                        )

            Thread(target=load_more).start()

    def previous(self):
        if self.results is None:
            return
        if hasattr(self.Parent, "searchResults"):
            videosBox = self.Parent.searchResults
        elif hasattr(self.Parent, "videosBox"):
            videosBox = self.Parent.videosBox
        elif hasattr(self.Parent, "home_feed_list"):
            videosBox = self.Parent.home_feed_list
        elif hasattr(self.Parent, "historyList"):
            videosBox = self.Parent.historyList
        else:
            videosBox = self.Parent.favList

        if not videosBox.Selection == 0:
            videosBox.Selection -= 1
            index = videosBox.Selection
            self.changeTrack(index)

    def onCopy(self, event):
        pyperclip.copy(self.url)
        wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def onBrowser(self, event):
        speak(_("جاري الفتح"))
        webbrowser.open(self.url)

    def onM4aDownload(self, event):
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(1, self.url, dlg, path=self.path)

    def onMp3Download(self, event):
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(2, self.url, dlg, path=self.path)

    def onVideoDownload(self, event):
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(0, self.url, dlg, path=self.path)

    def onDirect(self, event):
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(
            int(config_get("defaultformat")), self.url, dlg, path=self.path
        )

    def onDescription(self, event):
        if hasattr(self, "description"):
            DescriptionDialog(self, self.description)
            return

        def extract_description_sync():
            try:
                speak(_("يتم الآن جلب وصف الفيديو"))
                # Use run_in_async_loop for the async call
                info = run_in_async_loop(Video.getInfo(self.url))
            except Exception as e:
                print(e)
                speak(_("هناك خطأ ما أدى إلى منع جلب وصف الفيديو"))
                return
            self.description = info["description"]
            wx.CallAfter(DescriptionDialog, self, self.description)

        Thread(target=extract_description_sync).start()

    def extract_description(self):
        try:
            # Use run_in_async_loop for the async call
            info = run_in_async_loop(Video.get(self.url))
        except Exception:
            return
        self.description = info["description"]
