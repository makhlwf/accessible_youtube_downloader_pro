import logging
import webbrowser
import pyperclip
import time
import wx
from language_handler import _
from gui.download_progress import DownloadProgress
from gui.activity_dialog import LoadingDialog
from nvda_client.client import speak
from settings_handler import config_get, config_set
import application
import utils
from utils import get_playable_stream
from download_handler.downloader import downloadAction
from gui.settings_dialog import SettingsDialog
from gui.description import DescriptionDialog
from gui.custom_controls import CustomButton
from gui.quality_selection import QualitySelectionDialog
from threading import Thread
from database import Continue
from media_player.player import Player, State

logger = logging.getLogger(__name__)


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
        self.is_live = not can_download
        self.seek = int(config_get("seek"))
        self.results = results
        self.audio_mode = audio_mode
        if hasattr(self.results, "scraper") and self.results.scraper:
            self.results.scraper.audio_mode = self.audio_mode
        self.current_quality = getattr(stream, "quality", None)
        self.path = config_get("path")
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.SetBackgroundColour(wx.BLACK)
        self.player = None
        self.extracting_description = False
        self.url = url
        self.rating = None
        self.like_count = None
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
        self.chaptersMenu = wx.Menu()
        self.chaptersMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        self.chaptersSubMenu = trackOptions.AppendSubMenu(
            self.chaptersMenu, _("الفصول")
        )

        descriptionItem = trackOptions.Append(-1, _("وصف الفيديو\tctrl+shift+d"))
        equalizerItem = trackOptions.Append(-1, _("المعادل... \tctrl+e"))
        self.likeItem = trackOptions.Append(-1, _("إعجاب (L)"))
        self.dislikeItem = trackOptions.Append(-1, _("عدم إعجاب (D)"))
        copyItem = trackOptions.Append(-1, _("نسخ رابط المقطع\tctrl+l"))
        browserItem = trackOptions.Append(-1, _("الفتح من خلال متصفح الإنترنت\tctrl+b"))
        settingsItem = trackOptions.Append(-1, _("الإعدادات...\talt+s"))
        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("D"), directDownloadItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("D"), descriptionItem.GetId()),
                (wx.ACCEL_CTRL, ord("E"), equalizerItem.GetId()),
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
        self.Bind(wx.EVT_MENU, self.onEqualizer, equalizerItem)
        self.Bind(wx.EVT_MENU, self.onLike, self.likeItem)
        self.Bind(wx.EVT_MENU, self.onDislike, self.dislikeItem)
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
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
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

        try:
            self.player = Player(
                stream.url,
                self.GetHandle() if not audio_mode else None,
                self,
                options=options,
            )
        except Exception as e:
            logger.exception("Failed to initialize media player")
            utils.show_error(_("لا يمكن تشغيل الرابط"), e, parent=self)
            self.closeAction()
            return
        Thread(target=self.fetch_qualities, daemon=True).start()
        Thread(target=self.fetch_chapters, daemon=True).start()
        if self.url in Continue.get_all() and config_get("continue"):
            self.player.media.set_position(Continue.get_all()[url])
        Thread(target=self.extract_description, daemon=True).start()
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

    def fetch_chapters(self):
        import logging

        logging.getLogger(__name__).debug(f"Fetching chapters for {self.url}")
        chapters = utils.get_video_chapters(self.url)
        logging.getLogger(__name__).debug(f"Fetched {len(chapters)} chapters")
        wx.CallAfter(self.populate_chapters_menu, chapters)

    def populate_chapters_menu(self, chapters):
        # Clear existing items
        for item in self.chaptersMenu.GetMenuItems():
            self.chaptersMenu.DestroyItem(item)

        if not chapters:
            self.chaptersMenu.Append(-1, _("لا توجد فصول متاحة")).Enable(False)
            return

        for chapter in chapters:
            title = chapter.get("title", _("فصل بدون عنوان"))
            time_ms = chapter.get("time_ms", 0)
            time_str = utils.time_formatting(time_ms // 1000)
            label = f"{title} ({time_str})"
            item = self.chaptersMenu.Append(-1, label)
            self.Bind(
                wx.EVT_MENU,
                lambda event, t=time_ms, n=title: self.on_seek_to_chapter(t, n),
                item,
            )

    def on_seek_to_chapter(self, time_ms, title):
        if self.player:
            self.player.media.set_time(time_ms)
            time_str = utils.time_formatting(time_ms // 1000)
            speak(_("الانتقال إلى {} في {}").format(title, time_str))

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

    def fetch_like_count(self):
        def _task():
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Fetching likes for {self.url}")
            likes = utils.get_video_likes(self.url)
            logger.info(f"Fetched likes: {likes}")
            if likes is not None:
                self.like_count = likes
                logger.info(f"Updated self.like_count to {self.like_count}")

        Thread(target=_task, daemon=True).start()

    def populate_quality_menu(self, qualities):
        # Clear existing items
        for item in self.qualityMenu.GetMenuItems():
            self.qualityMenu.DestroyItem(item)

        if not qualities:
            self.qualityMenu.Append(-1, _("لا توجد جودات متاحة")).Enable(False)
            return

        for q in qualities:
            label = f"{q}{_('ك.ب/ث')}" if self.audio_mode else f"{q}{_('ب')}"
            item = self.qualityMenu.AppendCheckItem(-1, label)
            if q == self.current_quality:
                item.Check(True)
            self.Bind(wx.EVT_MENU, lambda event, h=q: self.on_change_quality(h), item)

    def on_change_quality(self, height):
        label = f"{height}{_('ك.ب/ث')}" if self.audio_mode else f"{height}{_('ب')}"
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

    def _download_media(self, option, url, dlg, path=None, quality=None):
        if path is None:
            path = self.path
        if option == 0:
            if quality:
                format = f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best"
            else:
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

    @has_player
    def playAction(self):
        state = self.player.media.get_state()
        if state in (State.NothingSpecial, State.Stopped, State.Ended):
            self.player.media.play()
        elif state in (State.Playing, State.Paused):
            if not self.is_live:
                self.player.media.pause()
            else:
                self.player.media.stop()

    @has_player
    def forwardAction(self):
        position = self.player.media.get_position()
        self.player.media.set_position(position + self.player.seek(self.seek))

    @has_player
    def rewindAction(self):
        position = self.player.media.get_position()
        self.player.media.set_position(position - self.player.seek(self.seek))

    @has_player
    def set_position(self, key):
        step = int(chr(key)) / 10
        self.player.media.set_position(step)
        speak(_("الوقت المنقضي: {}").format(self.player.get_elapsed()))

    @has_player
    def beginingAction(self):
        self.player.media.set_position(0.0)
        speak(_("بداية المقطع"))
        if self.player.media.get_state() in (
            State.NothingSpecial,
            State.Stopped,
            State.Ended,
        ):
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
            if hasattr(self.player.media, "close"):
                self.player.media.close()
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

    def onLike(self, event=None):
        if self.rating == "like":
            action = "remove_like"
            msg = _("تمت إزالة التقييم")
            self.rating = None
        else:
            action = "like"
            msg = _("تم الإعجاب")
            self.rating = "like"

        Thread(target=utils.like_video, args=(self.url, action), daemon=True).start()
        speak(msg)

    def onDislike(self, event=None):
        if self.rating == "dislike":
            action = "remove_like"
            msg = _("تمت إزالة التقييم")
            self.rating = None
        else:
            action = "dislike"
            msg = _("تم عدم الإعجاب")
            self.rating = "dislike"

        Thread(target=utils.like_video, args=(self.url, action), daemon=True).start()
        speak(msg)

    def onKeyDown(self, event):
        event.Skip()
        if event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_PAUSE):
            self.playAction()
        elif event.GetKeyCode() == wx.WXK_RIGHT and not event.HasAnyModifiers():
            self.forwardAction()
        elif event.GetKeyCode() == wx.WXK_LEFT and not event.HasAnyModifiers():
            self.rewindAction()
        elif event.ControlDown() and event.GetKeyCode() == wx.WXK_RIGHT:
            self.next()
        elif event.ControlDown() and event.GetKeyCode() == wx.WXK_LEFT:
            self.previous()
        elif event.GetKeyCode() == wx.WXK_UP and not event.HasAnyModifiers():
            self.increase_volume()
        elif event.GetKeyCode() == wx.WXK_DOWN and not event.HasAnyModifiers():
            self.decrease_volume()
        elif event.GetKeyCode() == ord("L") and not event.HasAnyModifiers():
            self.onLike()
        elif event.GetKeyCode() == ord("D") and not event.HasAnyModifiers():
            self.onDislike()
        elif event.GetKeyCode() == wx.WXK_UP and event.ShiftDown():
            if self.player is not None:
                rate = round(
                    self.player.media.get_rate() + config_get("playback_speed_step"), 2
                )
                self.player.media.set_rate(rate)
                speak(f"{rate}x")
        elif event.GetKeyCode() == wx.WXK_DOWN and event.ShiftDown():
            if self.player is not None:
                rate = round(
                    self.player.media.get_rate() - config_get("playback_speed_step"), 2
                )
                if rate < 0.1:
                    rate = 0.1
                self.player.media.set_rate(rate)
                speak(f"{rate}x")
        elif event.GetKeyCode() == wx.WXK_HOME:
            self.beginingAction()
        elif event.GetKeyCode() in range(49, 58):
            self.set_position(event.GetKeyCode())
        elif (
            event.ControlDown() and event.ShiftDown() and event.GetKeyCode() == ord("L")
        ):
            self.get_duration()
        elif event.ShiftDown() and event.GetKeyCode() == ord("L"):
            if self.like_count is not None:
                speak(_("{} إعجاب").format(self.like_count))
            else:
                speak(_("معلومات الإعجابات غير متوفرة بعد"))
        elif (
            event.ControlDown() and event.ShiftDown() and event.GetKeyCode() == ord("T")
        ):
            if self.player is not None:
                elapsed = self.player.get_elapsed()
                if elapsed == "":
                    speak(_("جاري جلب المعلومات..."))
                else:
                    speak(_("الوقت المنقضي: {}").format(elapsed))
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

        elif event.GetKeyCode() == ord("R") and event.ControlDown():
            if config_get("repeatTracks"):
                config_set("repeatTracks", False)

                speak(_("التكرار متوقف"))
            else:
                config_set("repeatTracks", True)

                speak(_("التكرار مفعل"))
                config_set("autonext", False)

        elif event.GetKeyCode() == ord("R"):
            if self.player is not None:
                remaining = self.player.get_remaining()
                if remaining == "":
                    speak(_("جاري جلب المعلومات..."))
                else:
                    speak(_("المتبقي: {}").format(remaining))

        elif event.GetKeyCode() == ord("E"):
            if self.player is not None:
                elapsed = self.player.get_elapsed()
                if elapsed == "":
                    speak(_("جاري جلب المعلومات..."))
                else:
                    speak(_("المنقضي: {}").format(elapsed))

        elif event.GetKeyCode() == ord("T"):
            if self.player is not None:
                duration = self.player.get_duration()
                if duration == "":
                    speak(_("جاري جلب المعلومات..."))
                else:
                    speak(_("الإجمالي: {}").format(duration))

        elif event.GetKeyCode() == ord("P"):
            if self.player is not None:
                percentage = self.player.get_position_percentage()
                if percentage < 0:
                    speak(_("جاري جلب المعلومات..."))
                else:
                    speak(_("{} بالمائة").format(percentage))

        elif event.GetKeyCode() == ord("N"):
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
        duration = self.player.get_duration()
        if duration == "":
            speak(_("جاري جلب المعلومات..."))
        else:
            speak(_("المدة: {}").format(duration))

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
        if hasattr(self, "description"):
            del self.description

        speak(_("جاري تشغيل {}").format(title))

        def _task():
            try:
                self.player.media.stop()
                stream = (
                    self.results.get_stream(index, audio_mode=self.audio_mode)
                    if hasattr(self.results, "get_stream")
                    else None
                )
                if stream is None:
                    stream = get_playable_stream(url, audio_mode=self.audio_mode)

                if stream:
                    wx.CallAfter(self._perform_track_change, stream, url, title)
                else:
                    wx.CallAfter(
                        utils.show_error,
                        _("تعذر جلب رابط التشغيل لهذا المقطع"),
                        parent=self,
                    )
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug(
                    f"Background description extraction failed: {e}"
                )
                wx.CallAfter(
                    utils.show_error,
                    _("حدث خطأ أثناء محاولة جلب رابط التشغيل"),
                    e,
                    self,
                )

        Thread(target=_task, daemon=True).start()

    def _perform_track_change(self, stream, url, title):
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
        self.SetTitle(f"{title} - {application.name}")
        self.like_count = None
        self.fetch_like_count()
        self.player.media.play()
        self.player.media.audio_set_volume(self.player.volume)
        Thread(target=self.extract_description, daemon=True).start()
        for item in self.qualityMenu.GetMenuItems():
            self.qualityMenu.DestroyItem(item)
        self.qualityMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        Thread(target=self.fetch_qualities, daemon=True).start()
        for item in self.chaptersMenu.GetMenuItems():
            self.chaptersMenu.DestroyItem(item)
        self.chaptersMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        Thread(target=self.fetch_chapters, daemon=True).start()
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
            box = self.Parent.searchResults
        elif hasattr(self.Parent, "videosBox"):
            box = self.Parent.videosBox
        elif hasattr(self.Parent, "home_feed_list"):
            box = self.Parent.home_feed_list
        elif hasattr(self.Parent, "historyList"):
            box = self.Parent.historyList
        elif hasattr(self.Parent, "favList"):
            box = self.Parent.favList
        else:
            return

        index = box.Selection
        if index == wx.NOT_FOUND or index >= box.GetCount() - 1:
            speak(_("نهاية القائمة"))
            return

        index += 1
        box.Selection = index
        self.changeTrack(index)

        # Trigger load more if near end
        count = (
            self.results.count if hasattr(self.results, "count") else len(self.results)
        )
        if index >= count - 2:

            def load_more():
                if hasattr(self.Parent, "searchResults"):
                    if self.results.load_more():
                        wx.CallAfter(
                            self.Parent.searchResults.Append,
                            self.results.get_last_titles(),
                        )
                elif hasattr(self.Parent, "videosBox"):
                    if self.results.next():
                        wx.CallAfter(
                            self.Parent.videosBox.Append, self.results.get_new_titles()
                        )

            Thread(target=load_more, daemon=True).start()

    def previous(self):
        if self.results is None:
            return
        if hasattr(self.Parent, "searchResults"):
            box = self.Parent.searchResults
        elif hasattr(self.Parent, "videosBox"):
            box = self.Parent.videosBox
        elif hasattr(self.Parent, "home_feed_list"):
            box = self.Parent.home_feed_list
        elif hasattr(self.Parent, "historyList"):
            box = self.Parent.historyList
        elif hasattr(self.Parent, "favList"):
            box = self.Parent.favList
        else:
            return

        index = box.Selection
        if index == wx.NOT_FOUND or index <= 0:
            speak(_("بداية القائمة"))
            return

        index -= 1
        box.Selection = index
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
        if not utils.check_yt_dlp(self):
            return
        qualities = LoadingDialog(
            self,
            _("جاري جلب الجودات المتاحة..."),
            utils.get_available_qualities,
            self.url,
        ).res
        quality = None
        if qualities:
            quality_dlg = QualitySelectionDialog(self, qualities)
            if quality_dlg.ShowModal() == wx.ID_OK:
                quality = quality_dlg.get_selected_quality()
            else:
                return
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(0, self.url, dlg, path=self.path, quality=quality)

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
                info = utils.get_media_info(self.url)
                if info and "description" in info:
                    self.description = info["description"]
                    wx.CallAfter(DescriptionDialog, self, self.description)
                else:
                    speak(_("تعذر جلب وصف الفيديو"))
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(
                    f"Manual description extraction failed: {e}"
                )
                speak(_("هناك خطأ ما أدى إلى منع جلب وصف الفيديو"))

        Thread(target=extract_description_sync, daemon=True).start()

    def onEqualizer(self, event):
        from gui.equalizer_dialog import EqualizerDialog
        from media_player.equalizer import EqualizerService

        EqualizerDialog(
            self,
            self.player.eq if self.player and self.player.eq else EqualizerService(),
        ).Show()

    def extract_description(self):
        if self.extracting_description or hasattr(self, "description"):
            return
        self.extracting_description = True
        try:
            info = utils.get_media_info(self.url)
            if info and "description" in info:
                self.description = info["description"]
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(
                f"Background description extraction failed: {e}"
            )
        finally:
            self.extracting_description = False
