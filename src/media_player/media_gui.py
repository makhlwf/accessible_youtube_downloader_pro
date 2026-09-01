import logging
import time
import webbrowser
from threading import Thread

import wx

import application
import utils
from database import Continue
from gui.activity_dialog import LoadingDialog
from gui.comments_dialog import CommentsDialog
from gui.custom_controls import CustomButton
from gui.description import DescriptionDialog
from gui.download_progress import DownloadProgress
from gui.quality_selection import QualitySelectionDialog
from gui.settings_dialog import SettingsDialog
from language_handler import _
from media_player.player import Player, State
from media_player.timecodes import format_timecode, parse_timecode
from settings_handler import config_get, config_set
from speech_client import speak
from sponsorblock_handler import (
    category_label,
    filter_skippable_segments,
    find_skip_segment,
    get_sponsorblock_segments,
    should_announce_skips,
)
from theme_handler import apply_theme
from utils import get_playable_stream

logger = logging.getLogger(__name__)


class AudioOutputDeviceDialog(wx.Dialog):
    def __init__(self, parent, devices, selected_device):
        wx.Dialog.__init__(self, parent, title=_("جهاز إخراج الصوت"))
        self.SetSize(450, 200)
        self.Centre()
        self.devices = [{"id": "", "description": _("جهاز إخراج الصوت الافتراضي")}]
        self.devices.extend(devices)

        panel = wx.Panel(self)
        label = wx.StaticText(panel, -1, _("جهاز إخراج الصوت: "))
        self.deviceBox = wx.Choice(
            panel,
            -1,
            choices=[device["description"] for device in self.devices],
        )
        self.deviceBox.Selection = self.get_selection_for_device(selected_device)
        okButton = wx.Button(panel, wx.ID_OK, _("مواف&ق"))
        okButton.SetDefault()
        cancelButton = wx.Button(panel, wx.ID_CANCEL, _("إل&غاء"))

        deviceSizer = wx.BoxSizer(wx.HORIZONTAL)
        deviceSizer.Add(label, 1)
        deviceSizer.Add(self.deviceBox, 2, wx.EXPAND)

        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer.Add(okButton, 1)
        buttonSizer.Add(cancelButton, 1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(deviceSizer, 1, wx.EXPAND)
        sizer.Add(buttonSizer, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        apply_theme(self)

    def get_selection_for_device(self, selected_device):
        for index, device in enumerate(self.devices):
            if device["id"] == selected_device:
                return index
        return 0

    def get_selected_device(self):
        return self.devices[self.deviceBox.Selection]


def has_player(method):
    def wrapper(self, *args, **kwargs):
        if self.player is not None:
            return method(self, *args, **kwargs)
        return None

    return wrapper


def diagnose_extraction_error(error_str: str) -> str:
    err_lower = str(error_str).lower()
    if "sign in" in err_lower or "confirm your age" in err_lower:
        return _(
            "هذا الفيديو يتطلب تسجيل الدخول أو إثبات العمر. يرجى ضبط ملف الكوكيز من الإعدادات."
        )
    if "private video" in err_lower or "video unavailable" in err_lower:
        return _("الفيديو غير متاح أو خاص.")
    return _("تعذر تشغيل المقطع: {}").format(error_str)


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
        shorts_mode=False,
    ):
        wx.Frame.__init__(self, parent, title=f"{title} - {application.name}")
        self.title = title
        self.is_live = not can_download
        self.can_download = can_download
        self.seek = int(config_get("seek"))
        self.results = results
        self.audio_mode = audio_mode
        self.shorts_mode = shorts_mode
        self.current_index = 0
        if isinstance(self.results, list):
            self.current_index = self._find_result_index(url) or 0
        self.preloaded_streams = {}
        self._preloading_in_progress = set()
        self._fetching_more_shorts = False
        if hasattr(self.results, "scraper") and self.results.scraper:
            self.results.scraper.audio_mode = self.audio_mode
        self.current_quality = getattr(stream, "quality", None)
        self.path = config_get("path")
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        self.SetBackgroundColour(wx.BLACK)
        self.player = None
        self._closing = False
        self.extracting_description = False
        self.url = url
        self.current_channel = self._resolve_channel(stream, url)
        self.rating = None
        self.rating_request_pending = False
        self.like_count = None
        self.available_subtitles = []
        self.current_subtitle_language = None
        self.current_subtitle_label = ""
        self.subtitle_cues = []
        self.subtitle_cues_language = None
        self.subtitles_enabled = False
        self.subtitle_loading = False
        self.subtitle_loading_key = None
        self.last_spoken_subtitle_index = -1
        self.subtitle_language_items = {}
        previousButton = CustomButton(self, -1, _("المقطع السابق"), name="controls")
        previousButton.Show() if self.results is not None else previousButton.Hide()
        beginingButton = CustomButton(self, -1, _("بداية المقطع"), name="controls")
        rewindButton = CustomButton(self, -1, _("إرجاع المقطع <"), name="controls")
        playButton = CustomButton(self, -1, _(r"تشغيل\إيقاف"), name="controls")
        forwardButton = CustomButton(self, -1, _("تقديم المقطع >"), name="controls")
        nextButton = CustomButton(self, -1, _("المقطع التالي"), name="controls")
        nextButton.Show() if self.results is not None else nextButton.Hide()
        self._previous_button = previousButton
        self._next_button = nextButton
        self._player_controls = [
            previousButton,
            beginingButton,
            rewindButton,
            playButton,
            forwardButton,
            nextButton,
        ]
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        for control in self.GetChildren():
            if control.Name == "controls":
                sizer1.Add(control, 1)
        sizer.AddStretchSpacer()
        sizer.Add(sizer1)
        self.SetSizer(sizer)
        apply_theme(self)
        if not self.audio_mode:
            self.SetBackgroundColour(wx.BLACK)
        menuBar = wx.MenuBar()
        trackOptions = wx.Menu()
        downloadMenu = wx.Menu()
        videoSubMenu = wx.Menu()
        mp4Item = videoSubMenu.Append(-1, "mp4")
        mkvItem = videoSubMenu.Append(-1, "mkv")
        downloadMenu.AppendSubMenu(videoSubMenu, _("فيديو"))

        audioMenu = wx.Menu()
        m4aItem = audioMenu.Append(-1, "m4a")
        mp3Item = audioMenu.Append(-1, "mp3")
        wavItem = audioMenu.Append(-1, "wav")
        flacItem = audioMenu.Append(-1, "flac")
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
        self.subtitlesMenu = wx.Menu()
        self.subtitlesEnableItem = self.subtitlesMenu.AppendCheckItem(
            -1, _("تشغيل الترجمة")
        )
        self.subtitlesLanguageMenu = wx.Menu()
        self.subtitlesLanguageMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        self.subtitlesMenu.AppendSubMenu(self.subtitlesLanguageMenu, _("لغة الترجمة"))
        trackOptions.AppendSubMenu(self.subtitlesMenu, _("الترجمة"))

        descriptionItem = trackOptions.Append(-1, _("وصف الفيديو\tctrl+shift+d"))
        commentsItem = trackOptions.Append(-1, _("تعليقات الفيديو\tctrl+shift+m"))
        jumpToTimeItem = trackOptions.Append(-1, _("الانتقال إلى وقت...\tctrl+g"))
        fullScreenItem = trackOptions.Append(-1, _("ملء الشاشة\tf11"))
        equalizerItem = trackOptions.Append(-1, _("المعادل... \tctrl+e"))
        audioOutputDeviceItem = trackOptions.Append(-1, _("جهاز إخراج الصوت...\tf12"))
        self.likeItem = trackOptions.Append(-1, _("إعجاب (L)"))
        self.dislikeItem = trackOptions.Append(-1, _("عدم إعجاب (D)"))
        copyItem = trackOptions.Append(-1, _("نسخ رابط المقطع\tctrl+l"))
        browserItem = trackOptions.Append(-1, _("الفتح من خلال متصفح الإنترنت\tctrl+b"))
        channelItem = trackOptions.Append(-1, _("الانتقال إلى القناة\tctrl+shift+c"))
        settingsItem = trackOptions.Append(-1, _("الإعدادات...\talt+s"))
        self.trackOptionsMenu = trackOptions
        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("D"), directDownloadItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("D"), descriptionItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("M"), commentsItem.GetId()),
                (wx.ACCEL_CTRL, ord("G"), jumpToTimeItem.GetId()),
                (wx.ACCEL_CTRL, ord("E"), equalizerItem.GetId()),
                (wx.ACCEL_NORMAL, wx.WXK_F11, fullScreenItem.GetId()),
                (wx.ACCEL_NORMAL, wx.WXK_F12, audioOutputDeviceItem.GetId()),
                (wx.ACCEL_CTRL, ord("L"), copyItem.GetId()),
                (wx.ACCEL_CTRL, ord("B"), browserItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("C"), channelItem.GetId()),
                (wx.ACCEL_ALT, ord("S"), settingsItem.GetId()),
            ]
        )
        self.SetAcceleratorTable(hotKeys)
        menuBar.Append(trackOptions, _("خيارات المقطع"))
        self.SetMenuBar(menuBar)
        self.Bind(wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mp4"), mp4Item)
        self.Bind(wx.EVT_MENU, lambda e: self.onVideoDownload(e, "mkv"), mkvItem)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "m4a"), m4aItem)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "mp3"), mp3Item)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "wav"), wavItem)
        self.Bind(wx.EVT_MENU, lambda e: self.onAudioDownload(e, "flac"), flacItem)
        self.Bind(wx.EVT_MENU, self.onDirect, directDownloadItem)
        self.Bind(wx.EVT_MENU, self.onToggleSubtitles, self.subtitlesEnableItem)
        self.Bind(wx.EVT_MENU, self.onDescription, descriptionItem)
        self.Bind(wx.EVT_MENU, self.onComments, commentsItem)
        self.Bind(wx.EVT_MENU, self.onJumpToTime, jumpToTimeItem)
        self.Bind(wx.EVT_MENU, lambda event: self.toggleFullScreen(), fullScreenItem)
        self.Bind(wx.EVT_MENU, self.onEqualizer, equalizerItem)
        self.Bind(wx.EVT_MENU, self.onAudioOutputDevice, audioOutputDeviceItem)
        self.Bind(wx.EVT_MENU, self.onLike, self.likeItem)
        self.Bind(wx.EVT_MENU, self.onDislike, self.dislikeItem)
        self.Bind(wx.EVT_MENU, self.onCopy, copyItem)
        self.Bind(wx.EVT_MENU, self.onBrowser, browserItem)
        self.Bind(wx.EVT_MENU, self.onOpenChannel, channelItem)
        self.Bind(wx.EVT_MENU, lambda event: SettingsDialog(self), settingsItem)
        self.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)
        self.prev_id = 100
        self.play_pause_id = 150
        self.next_id = 200
        self.registerHotKey()
        for hot_id in [self.prev_id, self.play_pause_id, self.next_id]:
            self.Bind(wx.EVT_HOTKEY, self.onHot, id=hot_id)
        for control in self.GetChildren():
            control.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
            control.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)
        previousButton.Bind(wx.EVT_BUTTON, lambda event: self.previous())
        beginingButton.Bind(wx.EVT_BUTTON, lambda event: self.beginingAction())
        rewindButton.Bind(wx.EVT_BUTTON, lambda event: self.rewindAction())
        playButton.Bind(wx.EVT_BUTTON, lambda event: self.playAction())
        forwardButton.Bind(wx.EVT_BUTTON, lambda event: self.forwardAction())
        nextButton.Bind(wx.EVT_BUTTON, lambda event: self.next())
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Show()
        # Focus the frame, not a control button: a focused wx.Button consumes the
        # space bar to activate itself, which toggles playback a second time on top
        # of onKeyDown and cancels the first toggle out. The frame also keeps focus
        # when the controls are hidden in fullscreen.
        self.SetFocus()
        if stream is None:
            utils.show_error(
                diagnose_extraction_error("No playable stream"), parent=self
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

        try:
            self.player = Player(
                stream.url,
                self.GetHandle() if not audio_mode else None,
                self,
                options=options,
            )
        except Exception as e:
            logger.exception("Failed to initialize media player")
            utils.show_error(diagnose_extraction_error(str(e)), parent=self)
            self.closeAction()
            return
        if config_get("player_fullscreen_default"):
            wx.CallAfter(self.toggleFullScreen, True)
        Thread(target=self.fetch_qualities, daemon=True).start()
        Thread(target=self.fetch_chapters, daemon=True).start()
        Thread(target=self.fetch_subtitles, daemon=True).start()
        self.fetch_like_count()
        all_continue = Continue.get_all() or {}
        if self.url in all_continue and config_get("continue"):
            self.player.media.set_position(all_continue[self.url])
        Thread(target=self.extract_description, daemon=True).start()
        self.history_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_history_timer, self.history_timer)
        self.history_timer.Start(10000)  # 10 seconds
        self.subtitle_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_subtitle_timer, self.subtitle_timer)
        self.sponsorblock_segments = []
        self._last_sponsorblock_skip_time = 0
        self._last_sponsorblock_target = None
        if config_get("sponsorblock"):
            if (
                hasattr(stream, "sponsorblock_segments")
                and stream.sponsorblock_segments is not None
            ):
                self.sponsorblock_segments = filter_skippable_segments(
                    stream.sponsorblock_segments
                )
            else:
                try:
                    self.sponsorblock_segments = get_sponsorblock_segments(self.url)
                except Exception:
                    logger.debug(
                        "Could not fetch SponsorBlock segments on MediaGui init",
                        exc_info=True,
                    )
            if self.sponsorblock_segments:
                initial_sec = 0.0
                if self.url in all_continue and config_get("continue"):
                    pos = all_continue[self.url]
                    if pos > 0:
                        length = self.player.get_length()
                        if length > 0:
                            initial_sec = pos * (length / 1000.0)
                match = find_skip_segment(initial_sec, self.sponsorblock_segments)
                if match is not None:
                    self.player.media.set_time(int(match[0] * 1000))
                    self._last_sponsorblock_skip_time = time.time()
                    self._last_sponsorblock_target = match[0]
                    self._announce_sponsorblock_skip(match[1])

        self.sponsorblock_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_sponsorblock_timer, self.sponsorblock_timer)
        if config_get("sponsorblock"):
            self.sponsorblock_timer.Start(150)
        watched_seconds = (
            self.player.media.get_time() / 1000
            if self.player.media.get_time() != -1
            else 0
        )
        self._report_watch_history(watched_seconds)
        if getattr(self, "shorts_mode", False):
            self._preload_next_shorts()

    def on_theme_applied(self, theme_name=None):
        if not self.audio_mode:
            self.SetBackgroundColour(wx.BLACK)

    def _resolve_channel(self, stream=None, url=None, index=None):
        channel_name = getattr(stream, "channel_name", "") if stream else ""
        channel_url = getattr(stream, "channel_url", "") if stream else ""
        if channel_url or channel_name:
            return {"name": channel_name or _("قناة"), "url": channel_url}

        if index is None:
            index = self._find_result_index(url or self.url)
        if index is None or self.results is None:
            return {"name": "", "url": ""}

        try:
            if hasattr(self.results, "get_channel"):
                channel = self.results.get_channel(index)
                return {
                    "name": channel.get("name") or _("قناة"),
                    "url": channel.get("url") or "",
                }
            if isinstance(self.results, list):
                row = self.results[index]
                return {
                    "name": row.get("channel_name") or row.get("author") or _("قناة"),
                    "url": row.get("channel_url") or "",
                }
        except Exception:
            logger.debug("Could not resolve channel for current media", exc_info=True)
        return {"name": "", "url": ""}

    def _find_result_index(self, url):
        if not url or self.results is None:
            return None
        try:
            if hasattr(self.results, "count") and hasattr(self.results, "get_url"):
                for index in range(self.results.count):
                    if self.results.get_url(index) == url:
                        return index
            if isinstance(self.results, list):
                for index, item in enumerate(self.results):
                    if item.get("url") == url:
                        return index
        except Exception:
            logger.debug("Could not find result index for %s", url, exc_info=True)
        return None

    def _history_metadata(self):
        channel = self.current_channel or {}
        return {
            "title": self.title,
            "channel_name": channel.get("name", ""),
            "channel_url": channel.get("url", ""),
            "is_live": self.is_live,
        }

    def _report_watch_history(self, watched_seconds=0):
        try:
            Thread(
                target=utils.update_watch_history,
                args=(self.url, watched_seconds),
                kwargs=self._history_metadata(),
                daemon=True,
            ).start()
        except Exception:
            pass

    def fetch_chapters(self):
        import logging

        logging.getLogger(__name__).debug(f"Fetching chapters for {self.url}")
        chapters = utils.get_video_chapters(self.url)
        logging.getLogger(__name__).debug(f"Fetched {len(chapters)} chapters")
        if self._closing:
            return
        wx.CallAfter(self.populate_chapters_menu, chapters)

    def fetch_subtitles(self):
        subtitles = utils.get_available_subtitles(self.url)
        if self._closing:
            return
        wx.CallAfter(self.populate_subtitles_menu, subtitles)

    def can_update_player_ui(self):
        try:
            return not self._closing and not self.IsBeingDeleted()
        except RuntimeError:
            return False

    def populate_chapters_menu(self, chapters):
        if not self.can_update_player_ui():
            return
        # Clear existing items
        try:
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
        except RuntimeError:
            logger.debug(
                "Skipping chapter menu update after player close", exc_info=True
            )

    def on_seek_to_chapter(self, time_ms, title):
        if self.player:
            self.player.media.set_time(time_ms)
            time_str = utils.time_formatting(time_ms // 1000)
            speak(_("الانتقال إلى {} في {}").format(title, time_str))

    def populate_subtitles_menu(self, subtitles):
        if not self.can_update_player_ui():
            return
        try:
            for item in self.subtitlesLanguageMenu.GetMenuItems():
                self.subtitlesLanguageMenu.DestroyItem(item)

            self.available_subtitles = list(subtitles or [])
            self.subtitle_language_items = {}

            if not self.available_subtitles:
                self.subtitlesLanguageMenu.Append(-1, _("لا توجد ترجمات متاحة")).Enable(
                    False
                )
                self.current_subtitle_language = None
                self.current_subtitle_label = ""
                self._set_subtitles_enabled(False, announce=False)
                return

            for subtitle in self.available_subtitles:
                label = subtitle.get("label") or subtitle.get("code") or ""
                item = self.subtitlesLanguageMenu.AppendCheckItem(-1, label)
                code = subtitle.get("code")
                self.subtitle_language_items[code] = item
                if code == self.current_subtitle_language:
                    item.Check(True)
                self.Bind(
                    wx.EVT_MENU,
                    lambda event, lang=code: self.onSelectSubtitleLanguage(lang),
                    item,
                )

            selected_available = (
                self.current_subtitle_language in self.subtitle_language_items
            )
            if self.current_subtitle_language and not selected_available:
                self.current_subtitle_language = None
                self.current_subtitle_label = ""
                self._set_subtitles_enabled(False, announce=False)
                return

            if self.subtitles_enabled and self.current_subtitle_language:
                self._load_selected_subtitle_cues()
        except RuntimeError:
            logger.debug(
                "Skipping subtitle menu update after player close", exc_info=True
            )

    def onToggleSubtitles(self, event=None):
        enabled = (
            self.subtitlesEnableItem.IsChecked()
            if hasattr(self.subtitlesEnableItem, "IsChecked")
            else not self.subtitles_enabled
        )
        if not enabled:
            self._set_subtitles_enabled(False)
            return

        if not self.available_subtitles:
            self._check_subtitles_enable_item(False)
            speak(_("لا توجد ترجمات متاحة"))
            return

        if not self.current_subtitle_language:
            if len(self.available_subtitles) == 1:
                self.onSelectSubtitleLanguage(self.available_subtitles[0]["code"])
            else:
                self._check_subtitles_enable_item(False)
                speak(_("اختر لغة الترجمة من القائمة"))
            return

        has_loaded_cues = (
            self.subtitle_cues
            and self.subtitle_cues_language == self.current_subtitle_language
        )
        self._set_subtitles_enabled(True, announce=has_loaded_cues)
        if not has_loaded_cues:
            speak(_("جاري تحميل الترجمة: {}").format(self.current_subtitle_label))
        self._load_selected_subtitle_cues()

    def onSelectSubtitleLanguage(self, language_code):
        subtitle = next(
            (
                subtitle
                for subtitle in self.available_subtitles
                if subtitle.get("code") == language_code
            ),
            None,
        )
        if subtitle is None:
            speak(_("لغة الترجمة غير متاحة"))
            return

        self.current_subtitle_language = language_code
        self.current_subtitle_label = subtitle.get("label") or language_code
        for code, item in self.subtitle_language_items.items():
            item.Check(code == language_code)
        self.subtitle_cues = []
        self.subtitle_cues_language = None
        self.subtitle_loading = False
        self.subtitle_loading_key = None
        self.last_spoken_subtitle_index = -1
        self._set_subtitles_enabled(True, announce=False)
        speak(_("جاري تحميل الترجمة: {}").format(self.current_subtitle_label))
        self._load_selected_subtitle_cues()

    def _set_subtitles_enabled(self, enabled, announce=True):
        self.subtitles_enabled = enabled
        self._check_subtitles_enable_item(enabled)
        if hasattr(self, "subtitle_timer"):
            if enabled and self.subtitle_cues:
                self.subtitle_timer.Start(250)
            else:
                self.subtitle_timer.Stop()
        if announce:
            if enabled:
                label = self.current_subtitle_label or _("الترجمة")
                speak(_("الترجمة مفعلة: {}").format(label))
            else:
                speak(_("الترجمة متوقفة"))

    def _check_subtitles_enable_item(self, checked):
        try:
            self.subtitlesEnableItem.Check(checked)
        except AttributeError:
            pass

    def _load_selected_subtitle_cues(self):
        if (
            not self.subtitles_enabled
            or not self.current_subtitle_language
            or self.subtitle_loading
        ):
            return
        if (
            self.subtitle_cues
            and self.subtitle_cues_language == self.current_subtitle_language
        ):
            self._set_subtitles_enabled(True, announce=False)
            return

        language_code = self.current_subtitle_language
        media_url = self.url
        self.subtitle_loading = True
        self.subtitle_loading_key = (media_url, language_code)

        def _task():
            cues = utils.get_subtitle_cues(media_url, language_code)
            if self._closing:
                return
            wx.CallAfter(self._on_subtitle_cues_loaded, media_url, language_code, cues)

        Thread(target=_task, daemon=True).start()

    def _on_subtitle_cues_loaded(self, media_url, language_code, cues):
        load_key = (media_url, language_code)
        if self.subtitle_loading_key == load_key:
            self.subtitle_loading = False
            self.subtitle_loading_key = None
        if (
            self._closing
            or media_url != self.url
            or language_code != self.current_subtitle_language
            or not self.subtitles_enabled
        ):
            return
        self.subtitle_cues = list(cues or [])
        self.subtitle_cues_language = language_code if self.subtitle_cues else None
        self.last_spoken_subtitle_index = -1
        if not self.subtitle_cues:
            self._set_subtitles_enabled(False, announce=False)
            speak(_("تعذر تحميل نص الترجمة"))
            return
        self._set_subtitles_enabled(True, announce=False)
        speak(_("تم تفعيل الترجمة: {}").format(self.current_subtitle_label))

    def on_subtitle_timer(self, event):
        if not self.subtitles_enabled or not self.subtitle_cues or self.player is None:
            return
        try:
            if self.player.media.get_state() != State.Playing:
                return
            current_ms = self.player.media.get_time()
        except Exception:
            return
        self._speak_due_subtitle(current_ms)

    def _speak_due_subtitle(self, current_ms):
        if current_ms is None or current_ms < 0:
            return
        if self.last_spoken_subtitle_index >= 0:
            last_cue = self.subtitle_cues[self.last_spoken_subtitle_index]
            if current_ms < last_cue["start_ms"]:
                self.last_spoken_subtitle_index = -1

        for index, cue in enumerate(self.subtitle_cues):
            if current_ms < cue["start_ms"]:
                break
            if cue["start_ms"] <= current_ms <= cue["end_ms"]:
                if index != self.last_spoken_subtitle_index:
                    self.last_spoken_subtitle_index = index
                    speak(cue["text"])
                break

    def reset_subtitles_for_media(self):
        self.available_subtitles = []
        self.subtitle_cues = []
        self.subtitle_cues_language = None
        self.subtitle_loading = False
        self.subtitle_loading_key = None
        self.last_spoken_subtitle_index = -1
        self.subtitle_language_items = {}
        if hasattr(self, "subtitle_timer"):
            self.subtitle_timer.Stop()
        try:
            for item in self.subtitlesLanguageMenu.GetMenuItems():
                self.subtitlesLanguageMenu.DestroyItem(item)
            self.subtitlesLanguageMenu.Append(-1, _("جاري التحميل...")).Enable(False)
        except RuntimeError:
            logger.debug(
                "Skipping subtitle menu reset after player close", exc_info=True
            )

    def on_history_timer(self, event):
        try:
            if self.player and self.player.media.get_state() == State.Playing:
                watched_seconds = self.player.media.get_time() / 1000
                if watched_seconds > 0:
                    self._report_watch_history(watched_seconds)
        except Exception:
            pass

    def on_sponsorblock_timer(self, event):
        if (
            not config_get("sponsorblock")
            or not self.sponsorblock_segments
            or self.player is None
            or self._closing
        ):
            return
        try:
            if self.player.media.get_state() != State.Playing:
                return
            current_ms = self.player.media.get_time()
        except Exception:
            return
        if current_ms is None or current_ms < 0:
            return
        current_sec = current_ms / 1000.0
        self._check_sponsorblock_skip(current_sec)

    def _announce_sponsorblock_skip(self, category=""):
        """Tell the user which kind of segment was just skipped, if enabled."""
        if not should_announce_skips():
            return
        label = category_label(category)
        if label:
            speak(_("تم تخطي مقطع {category}").format(category=label))
        else:
            speak(_("تم تخطي مقطع SponsorBlock"))

    def _check_sponsorblock_skip(self, current_sec):
        if self._last_sponsorblock_target is not None:
            if (
                time.time() - self._last_sponsorblock_skip_time < 1.0
                and current_sec < self._last_sponsorblock_target
            ):
                return
            self._last_sponsorblock_target = None

        match = find_skip_segment(current_sec, self.sponsorblock_segments)
        if match is not None:
            target, category = match
            logger.info("SponsorBlock: skipping at %.2fs to %.2fs", current_sec, target)
            self._last_sponsorblock_skip_time = time.time()
            self._last_sponsorblock_target = target
            self.player.media.set_time(int(target * 1000))
            self._announce_sponsorblock_skip(category)

    def fetch_qualities(self):
        qualities = utils.get_available_qualities(self.url, audio_mode=self.audio_mode)
        if self._closing:
            return
        wx.CallAfter(self.populate_quality_menu, qualities)

    def fetch_like_count(self):
        def _task():
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Fetching likes for {self.url}")
            like_info = utils.get_video_like_info(self.url)
            logger.info(f"Fetched like info: {like_info}")
            likes = like_info.get("likes")
            if likes is not None:
                self.like_count = likes
                logger.info(f"Updated self.like_count to {self.like_count}")
            if not self.rating_request_pending:
                self.rating = like_info.get("rating")
                logger.info(f"Updated self.rating to {self.rating}")

        Thread(target=_task, daemon=True).start()

    def populate_quality_menu(self, qualities):
        if not self.can_update_player_ui():
            return
        # Clear existing items
        try:
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
                self.Bind(
                    wx.EVT_MENU, lambda event, h=q: self.on_change_quality(h), item
                )
        except RuntimeError:
            logger.debug(
                "Skipping quality menu update after player close", exc_info=True
            )

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

    def _download_media(self, format_type, url, dlg, path=None, quality=None):
        from download_handler.downloader import start_media_download

        start_media_download(
            url,
            format_type,
            self,
            path=path,
            title=self.title,
            quality=quality,
            folder=False,
        )

    @has_player
    def playAction(self):
        state = self.player.media.get_state()
        if state in (State.NothingSpecial, State.Stopped, State.Ended):
            if state == State.Ended:
                self.player.media.set_position(0.0)
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

    @has_player
    def seek_to_seconds(self, seconds, label=None):
        try:
            seconds = max(0, int(seconds))
        except TypeError, ValueError:
            speak(_("صيغة الوقت غير صحيحة"))
            return False

        milliseconds = seconds * 1000
        self.player.media.set_time(milliseconds)
        self.last_spoken_subtitle_index = -1
        label = label or format_timecode(seconds)
        speak(_("الانتقال إلى {}").format(label))
        return True

    @has_player
    def seek_to_timecode(self, value):
        seconds = parse_timecode(value)
        if seconds is None:
            speak(_("صيغة الوقت غير صحيحة. استخدم مثلًا 2:47 أو 1:02:03"))
            return False
        return self.seek_to_seconds(seconds, format_timecode(seconds))

    @has_player
    def onJumpToTime(self, event=None):
        current_value = ""
        try:
            current_ms = self.player.media.get_time()
            if current_ms >= 0:
                current_value = format_timecode(current_ms // 1000)
        except Exception:
            current_value = ""

        dlg = wx.TextEntryDialog(
            self,
            _("أدخل الوقت بصيغة 2:47 أو 1:02:03"),
            _("الانتقال إلى وقت"),
            current_value,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            self.seek_to_timecode(dlg.GetValue())
        finally:
            dlg.Destroy()

    def onClose(self, event):
        self.closeAction()

    def onCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.closeAction()
            return
        if self._is_context_menu_key(event):
            event.Skip(False)
            self.onContextMenu(event)
            return
        event.Skip()

    def closeAction(self):
        if self._closing:
            return
        self._closing = True
        if hasattr(self, "history_timer"):
            try:
                self.history_timer.Stop()
            except Exception:
                logger.debug("Could not stop history timer during close", exc_info=True)
        if hasattr(self, "subtitle_timer"):
            try:
                self.subtitle_timer.Stop()
            except Exception:
                logger.debug(
                    "Could not stop subtitle timer during close", exc_info=True
                )
        if hasattr(self, "sponsorblock_timer"):
            try:
                self.sponsorblock_timer.Stop()
            except Exception:
                logger.debug(
                    "Could not stop sponsorblock timer during close", exc_info=True
                )
        player = self.player
        self.player = None
        if player is not None:
            try:
                position = player.media.get_position()
                all_continue = Continue.get_all() or {}
                if position in (0.0, -1) and self.url in all_continue:
                    Continue.remove_continue(self.url)
                elif self.url in all_continue:
                    Continue.update(self.url, position)
                else:
                    Continue.new_continue(self.url, position)
            except Exception:
                logger.debug(
                    "Could not save playback position during close", exc_info=True
                )

            # Final history update
            try:
                watched_seconds = player.media.get_time() / 1000
                if watched_seconds > 0:
                    self._report_watch_history(watched_seconds)
            except Exception:
                pass

            player.close()
        parent = self.GetParent()
        if parent is not None:
            try:
                parent.Show()
            except Exception:
                logger.debug("Could not show parent after media close", exc_info=True)

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

    def onContextMenu(self, event=None):
        if hasattr(self, "trackOptionsMenu"):
            self.PopupMenu(self.trackOptionsMenu)

    def toggleRepeatTracks(self, event=None):
        if config_get("repeatTracks"):
            config_set("repeatTracks", False)
            speak(_("التكرار متوقف"))
            return

        config_set("repeatTracks", True)
        config_set("autonext", False)
        speak(_("التكرار مفعل"))

    def toggleAutoNext(self, event=None):
        if config_get("autonext"):
            config_set("autonext", False)
            speak(_("تشغيل المقطع التالي تلقائيًا متوقف"))
            return

        config_set("autonext", True)
        config_set("repeatTracks", False)
        speak(_("تشغيل المقطع التالي تلقائيًا مفعل"))

    def _is_context_menu_key(self, event):
        key = event.GetKeyCode()
        f10_key = getattr(wx, "WXK_F10", None)
        if isinstance(f10_key, int) and key == f10_key and event.ShiftDown():
            return True
        for key_name in ("WXK_MENU", "WXK_WINDOWS_MENU"):
            key_code = getattr(wx, key_name, None)
            if isinstance(key_code, int) and key == key_code:
                return True
        return False

    def onLike(self, event=None):
        if self.rating == "like":
            action = "remove_like"
            msg = _("تمت إزالة التقييم")
            new_rating = None
        else:
            action = "like"
            msg = _("تم الإعجاب")
            new_rating = "like"

        self._submit_rating_change(action, new_rating, msg)

    def onDislike(self, event=None):
        if self.rating == "dislike":
            action = "remove_like"
            msg = _("تمت إزالة التقييم")
            new_rating = None
        else:
            action = "dislike"
            msg = _("تم عدم الإعجاب")
            new_rating = "dislike"

        self._submit_rating_change(action, new_rating, msg)

    def _submit_rating_change(self, action, new_rating, success_message):
        if self.rating_request_pending:
            speak(_("جاري تحديث التقييم"))
            return

        previous_rating = self.rating
        self.rating_request_pending = True

        def _task():
            res = utils.like_video(self.url, action, parent=self)
            self.rating_request_pending = False
            if res.get("success"):
                self.rating = new_rating
                speak(success_message)
                self.fetch_like_count()
                return

            if self.rating == new_rating:
                self.rating = previous_rating

            err = res.get("error") or _("تعذر تحديث التقييم")
            wx.CallAfter(speak, err)

        Thread(target=_task, daemon=True).start()

    def onKeyDown(self, event):
        event.Skip()
        if self._is_context_menu_key(event):
            event.Skip(False)
            self.onContextMenu(event)
        elif event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_PAUSE):
            # Consume the key so a control button that has focus (after a mouse
            # click, say) does not also activate and undo the toggle.
            event.Skip(False)
            self.playAction()
        elif event.GetKeyCode() == wx.WXK_RIGHT and not event.HasAnyModifiers():
            self.forwardAction()
        elif event.GetKeyCode() == wx.WXK_LEFT and not event.HasAnyModifiers():
            self.rewindAction()
        elif event.ControlDown() and event.GetKeyCode() == wx.WXK_RIGHT:
            self.next()
        elif event.ControlDown() and event.GetKeyCode() == wx.WXK_LEFT:
            self.previous()
        elif (
            getattr(self, "shorts_mode", False)
            and event.GetKeyCode() == wx.WXK_UP
            and event.ShiftDown()
        ):
            self.increase_volume()
        elif (
            getattr(self, "shorts_mode", False)
            and event.GetKeyCode() == wx.WXK_DOWN
            and event.ShiftDown()
        ):
            self.decrease_volume()
        elif (
            getattr(self, "shorts_mode", False)
            and event.GetKeyCode() == wx.WXK_UP
            and not event.HasAnyModifiers()
        ):
            self.previous()
        elif (
            getattr(self, "shorts_mode", False)
            and event.GetKeyCode() == wx.WXK_DOWN
            and not event.HasAnyModifiers()
        ):
            self.next()
        elif event.GetKeyCode() == wx.WXK_UP and not event.HasAnyModifiers():
            self.increase_volume()
        elif event.GetKeyCode() == wx.WXK_DOWN and not event.HasAnyModifiers():
            self.decrease_volume()
        elif event.GetKeyCode() == wx.WXK_F12:
            event.Skip(False)
            self.onAudioOutputDevice(event)
        elif event.GetKeyCode() == wx.WXK_F11:
            event.Skip(False)
            self.toggleFullScreen()
        elif (
            event.ControlDown()
            and not event.ShiftDown()
            and event.GetKeyCode() == ord("G")
        ):
            event.Skip(False)
            self.onJumpToTime(event)
        elif event.GetKeyCode() == ord("L") and not event.HasAnyModifiers():
            self.onLike()
        elif event.GetKeyCode() == ord("D") and not event.HasAnyModifiers():
            self.onDislike()
        elif event.ShiftDown() and (
            event.GetKeyCode() in (ord("."), ord(">"))
            or event.GetUnicodeKey() in (ord("."), ord(">"))
        ):
            if self.player is not None:
                rate = round(
                    self.player.media.get_rate() + config_get("playback_speed_step"), 2
                )
                self.player.media.set_rate(rate)
                speak(f"{rate}x")
        elif event.ShiftDown() and (
            event.GetKeyCode() in (ord(","), ord("<"))
            or event.GetUnicodeKey() in (ord(","), ord("<"))
        ):
            if self.player is not None:
                rate = round(
                    self.player.media.get_rate() - config_get("playback_speed_step"), 2
                )
                rate = max(rate, 0.1)
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

            self.seek = max(self.seek, 1)

            speak("{} {} {}".format(_("تحريك المقطع"), self.seek, _("ثانية/ثواني")))

            config_set("seek", self.seek)

        elif event.GetKeyCode() in (ord("="), wx.WXK_NUMPAD_ADD):
            self.seek += 1

            self.seek = min(self.seek, 10)

            speak("{} {} {}".format(_("تحريك المقطع"), self.seek, _("ثانية/ثواني")))

            config_set("seek", self.seek)

        elif event.GetKeyCode() == ord("R") and event.ControlDown():
            self.toggleRepeatTracks()

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
            self.toggleAutoNext()

        elif event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.toggleFullScreen()

        elif event.GetKeyCode() == wx.WXK_ALT:
            if self.IsFullScreen():
                self.toggleFullScreen(False)

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

    @has_player
    def onAudioOutputDevice(self, event=None):
        devices = self.player.get_audio_output_devices()
        selected_device = self.player.get_selected_audio_output_device()
        dlg = AudioOutputDeviceDialog(self, devices, selected_device)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            device = dlg.get_selected_device()
            if self.player.select_audio_output_device(device["id"]):
                speak(
                    _("تم تغيير جهاز إخراج الصوت إلى {}").format(device["description"])
                )
            else:
                speak(
                    _(
                        "جهاز إخراج الصوت المحدد غير متاح. سيتم استخدام جهاز إخراج الصوت الافتراضي"
                    )
                )
        finally:
            dlg.Destroy()

    def on_audio_output_fallback(self):
        wx.CallAfter(
            speak,
            _(
                "جهاز إخراج الصوت المحدد غير متاح. سيتم استخدام جهاز إخراج الصوت الافتراضي"
            ),
        )

    def _preload_next_shorts(self):
        if (
            not getattr(self, "shorts_mode", False)
            or not isinstance(getattr(self, "results", None), list)
            or getattr(self, "_closing", False)
        ):
            return

        curr = self.current_index
        targets = []
        for offset in (-1, 1, 2):
            idx = curr + offset
            if 0 <= idx < len(self.results):
                item_url = self.results[idx].get("url")
                if (
                    item_url
                    and item_url not in self.preloaded_streams
                    and item_url not in self._preloading_in_progress
                ):
                    targets.append((idx, item_url))

        if curr >= len(self.results) - 3:
            self._fetch_more_shorts()

        for idx, item_url in targets:
            self._preloading_in_progress.add(item_url)

            def _preload_job(target_idx=idx, target_url=item_url):
                try:
                    s = get_playable_stream(target_url, audio_mode=self.audio_mode)
                    if s and not getattr(self, "_closing", False):
                        self.preloaded_streams[target_url] = s
                        if (
                            hasattr(s, "title")
                            and s.title
                            and s.title.strip()
                            and isinstance(self.results, list)
                            and 0 <= target_idx < len(self.results)
                        ):
                            self.results[target_idx]["title"] = s.title
                except Exception as e:
                    logger.debug(f"Preloading stream failed for {target_url}: {e}")
                finally:
                    self._preloading_in_progress.discard(target_url)

            Thread(target=_preload_job, daemon=True).start()

    def _fetch_more_shorts(self):
        if (
            getattr(self, "_fetching_more_shorts", False)
            or not isinstance(self.results, list)
            or not self.results
        ):
            return
        self._fetching_more_shorts = True

        def _task():
            try:
                last_id = self.results[-1].get("id")
                more_shorts = utils.get_shorts_feed(seed_video_id=last_id)
                if more_shorts and not self._closing:
                    existing_ids = {
                        item.get("id")
                        for item in self.results
                        if isinstance(item, dict)
                    }
                    new_items = [
                        s
                        for s in more_shorts
                        if isinstance(s, dict) and s.get("id") not in existing_ids
                    ]
                    if new_items:
                        self.results.extend(new_items)
                        self._preload_next_shorts()
            except Exception as e:
                logger.debug(f"Failed to fetch more shorts: {e}")
            finally:
                self._fetching_more_shorts = False

        Thread(target=_task, daemon=True).start()

    def _resolve_channel(self, stream=None, url=None, index=None):
        channel_name = getattr(stream, "channel_name", "") if stream else ""
        channel_url = getattr(stream, "channel_url", "") if stream else ""
        if channel_url or channel_name:
            return {"name": channel_name or _("قناة"), "url": channel_url}
        if (
            index is not None
            and isinstance(self.results, list)
            and 0 <= index < len(self.results)
        ):
            author = self.results[index].get("author")
            if author:
                return {"name": author, "url": ""}
        return {"name": _("قناةغيرمعروفة"), "url": ""}

    def _set_player_controls_visible(self, visible):
        for control in getattr(self, "_player_controls", []):
            show = bool(visible)
            if control in (self._previous_button, self._next_button):
                show = show and self.results is not None
            try:
                control.Show(show)
            except RuntimeError:
                logger.debug("Could not update fullscreen controls", exc_info=True)
        try:
            self.Layout()
        except RuntimeError:
            logger.debug("Could not lay out fullscreen controls", exc_info=True)

    def toggleFullScreen(self, show=None):
        if show is None:
            show = not self.IsFullScreen()
        try:
            self.ShowFullScreen(show, wx.FULLSCREEN_ALL)
        except TypeError:
            self.ShowFullScreen(show)
        self._set_player_controls_visible(not show)
        if self.IsFullScreen():
            speak(_("وضع ملء الشاشة مفعل"))
        else:
            speak(_("وضع ملء الشاشة متوقف"))

    def _has_parent_listbox(self):
        if not self.Parent:
            return False
        return any(
            hasattr(self.Parent, attr)
            for attr in (
                "searchResults",
                "videosBox",
                "itemsBox",
                "home_feed_list",
                "historyList",
                "favList",
            )
        )

    def changeTrack(self, index):
        if self._closing or self.player is None:
            return
        self.current_index = index
        if hasattr(self.results, "scraper"):
            self.results.scraper.add_item(index, priority=0)
        if not isinstance(self.results, list):
            url = self.results.get_url(index)
            title = self.results.get_title(index)
        else:
            url = self.results[index]["url"]
            title = self.results[index]["title"]
            if getattr(self, "shorts_mode", False) and url in self.preloaded_streams:
                ps = self.preloaded_streams[url]
                if hasattr(ps, "title") and ps.title and ps.title.strip():
                    title = ps.title
                    self.results[index]["title"] = title
        if hasattr(self, "description"):
            del self.description

        speak(_("جاري تشغيل {}").format(title))

        if getattr(self, "shorts_mode", False):
            self._preload_next_shorts()

        if getattr(self, "shorts_mode", False) and url in getattr(
            self, "preloaded_streams", {}
        ):
            stream = self.preloaded_streams.get(url)
            if stream:
                self.player.media.stop()
                self._perform_track_change(stream, url, title, index)
                return

        def _task():
            try:
                if self._closing or self.player is None:
                    return
                self.player.media.stop()
                stream = None
                if getattr(self, "shorts_mode", False) and url in getattr(
                    self, "preloaded_streams", {}
                ):
                    stream = self.preloaded_streams.get(url)

                if stream is None and hasattr(self.results, "get_stream"):
                    stream = self.results.get_stream(index, audio_mode=self.audio_mode)

                if stream is None:
                    stream = get_playable_stream(url, audio_mode=self.audio_mode)

                if stream:
                    if self._closing:
                        return
                    wx.CallAfter(self._perform_track_change, stream, url, title, index)
                else:
                    wx.CallAfter(
                        utils.show_error,
                        diagnose_extraction_error("No playable stream URL returned"),
                        parent=self,
                    )
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug(
                    f"Background stream extraction failed: {e}"
                )
                wx.CallAfter(
                    utils.show_error,
                    diagnose_extraction_error(str(e)),
                    parent=self,
                )

        Thread(target=_task, daemon=True).start()

    def _perform_track_change(self, stream, url, title, index=None):
        if self._closing or self.player is None:
            return
        if hasattr(stream, "title") and stream.title and stream.title.strip():
            title = stream.title
            if (
                getattr(self, "shorts_mode", False)
                and isinstance(self.results, list)
                and index is not None
                and 0 <= index < len(self.results)
            ):
                self.results[index]["title"] = title
        options = []
        if hasattr(stream, "headers") and stream.headers:
            ua = stream.headers.get("User-Agent")
            if ua:
                options.append(f":http-user-agent={ua}")
        if hasattr(stream, "audio_url") and stream.audio_url:
            options.append(f":input-slave={stream.audio_url}")
        if self.audio_mode:
            options.append(":no-video")
        if getattr(self, "shorts_mode", False):
            options.append("loop-file=inf")

        self.player.set_media(stream.url, options=options)
        self.url = url
        self.title = title
        self.reset_subtitles_for_media()
        self.current_channel = self._resolve_channel(stream, url, index)
        self.SetTitle(f"{title} - {application.name}")
        self.like_count = None
        self.rating = None
        self.rating_request_pending = False
        self.fetch_like_count()
        self.player.media.play()
        self.player.media.audio_set_volume(self.player.volume)
        self.sponsorblock_segments = []
        self._last_sponsorblock_skip_time = 0
        self._last_sponsorblock_target = None
        if config_get("sponsorblock"):
            if (
                hasattr(stream, "sponsorblock_segments")
                and stream.sponsorblock_segments is not None
            ):
                self.sponsorblock_segments = filter_skippable_segments(
                    stream.sponsorblock_segments
                )
            else:
                try:
                    self.sponsorblock_segments = get_sponsorblock_segments(url)
                except Exception:
                    pass
            if self.sponsorblock_segments:
                match = find_skip_segment(0.0, self.sponsorblock_segments)
                if match is not None:
                    self.player.media.set_time(int(match[0] * 1000))
                    self._last_sponsorblock_skip_time = time.time()
                    self._last_sponsorblock_target = match[0]
                    self._announce_sponsorblock_skip(match[1])
            if (
                hasattr(self, "sponsorblock_timer")
                and not self.sponsorblock_timer.IsRunning()
            ):
                self.sponsorblock_timer.Start(150)
        if not getattr(self, "shorts_mode", False):
            Thread(target=self.extract_description, daemon=True).start()
            for item in self.qualityMenu.GetMenuItems():
                self.qualityMenu.DestroyItem(item)
            self.qualityMenu.Append(-1, _("جاري التحميل...")).Enable(False)
            Thread(target=self.fetch_qualities, daemon=True).start()
            for item in self.chaptersMenu.GetMenuItems():
                self.chaptersMenu.DestroyItem(item)
            self.chaptersMenu.Append(-1, _("جاري التحميل...")).Enable(False)
            Thread(target=self.fetch_chapters, daemon=True).start()
            Thread(target=self.fetch_subtitles, daemon=True).start()
        # Report new track to history
        self._report_watch_history(0)

    def next(self):
        if self.results is None:
            return

        if getattr(self, "shorts_mode", False) or (
            isinstance(self.results, list) and not self._has_parent_listbox()
        ):
            count = len(self.results)
            if self.current_index >= count - 1:
                speak(_("نهاية القائمة"))
                return
            self.current_index += 1
            self.changeTrack(self.current_index)
            return

        if hasattr(self.Parent, "searchResults"):
            box = self.Parent.searchResults
        elif hasattr(self.Parent, "videosBox"):
            box = self.Parent.videosBox
        elif hasattr(self.Parent, "itemsBox"):
            box = self.Parent.itemsBox
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
                elif hasattr(self.Parent, "videosBox") and self.results.next():
                    wx.CallAfter(
                        self.Parent.videosBox.Append, self.results.get_new_titles()
                    )

            Thread(target=load_more, daemon=True).start()

    def previous(self):
        if self.results is None:
            return

        if getattr(self, "shorts_mode", False) or (
            isinstance(self.results, list) and not self._has_parent_listbox()
        ):
            if self.current_index <= 0:
                speak(_("بداية القائمة"))
                return
            self.current_index -= 1
            self.changeTrack(self.current_index)
            return

        if hasattr(self.Parent, "searchResults"):
            box = self.Parent.searchResults
        elif hasattr(self.Parent, "videosBox"):
            box = self.Parent.videosBox
        elif hasattr(self.Parent, "itemsBox"):
            box = self.Parent.itemsBox
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
        utils.copy_to_clipboard(self.url)
        wx.MessageBox(_("تم نسخ رابط المقطع بنجاح"), _("اكتمال"), parent=self)

    def onBrowser(self, event):
        speak(_("جاري الفتح"))
        webbrowser.open(self.url)

    def onOpenChannel(self, event):
        channel = self.current_channel or {}
        if not channel.get("url"):
            speak(_("رابط القناة غير متوفر"))
            return
        from gui.channel_dialog import ChannelDialog

        ChannelDialog(self, channel["url"], channel.get("name") or _("قناة"))

    def onAudioDownload(self, event, format_type):
        dlg = DownloadProgress(wx.GetApp().GetTopWindow(), self.title)
        self._download_media(format_type, self.url, dlg, path=self.path)

    def onVideoDownload(self, event, format_type):
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
        self._download_media(
            format_type, self.url, dlg, path=self.path, quality=quality
        )

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

    def onComments(self, event):
        CommentsDialog(
            self,
            video_url=self.url,
            title=self.title,
            timestamp_callback=self.seek_to_seconds,
        )

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
