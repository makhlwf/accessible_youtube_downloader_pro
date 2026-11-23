"""The desktop home window and its event handlers."""

import json
import logging
import os
import threading
import webbrowser

import pyperclip
import wx

import application
import paths
import utils
from app_runtime import browser_extension_manager, windows_url_association
from app_runtime.async_utils import stop_async_loop
from app_runtime.ipc import start_ipc_server
from app_state import database, settings_handler
from gui.activity_dialog import LoadingDialog
from gui.custom_controls import CustomLabel
from gui.theme_handler import apply_theme
from gui.tray_icon import TaskBarIcon
from language_handler import _, init_translation
from speech_client import speak
from youtube_backend.deno_service import deno_service
from youtube_backend.pot_provider_service import pot_service
from youtube_browser.scraper import Scraper

# NOTE: heavy, feature-specific modules (media_gui/mpv, the YouTube browser,
# per-feature dialogs, yt-dlp) are intentionally NOT imported here. They are
# imported lazily inside the handler that first needs them so the home screen
# can appear without paying their (~1s combined) import cost at launch.


logger = logging.getLogger(__name__)


class HomeScreen(wx.Frame):
    def __init__(self, start_hidden=False, launch_url=""):
        wx.Frame.__init__(self, parent=None, title=application.name)
        settings_handler.config_initialization()
        init_translation("HexPlayer")

        self.checked = False
        self._shutting_down = threading.Event()
        self.home_feed_data = []
        self.home_feed_results = None
        self._home_feed_request = None
        self.scraper = Scraper(owner=self)
        self.home_feed_continuation = None
        self.last_clip_content = ""
        self.pending_launch_url = launch_url
        self.tray_icon = TaskBarIcon(self)

        self._init_ui()
        apply_theme(self)
        self._setup_menus()
        self._bind_events()
        # Cheap and affects the initial control set (the Shorts button/menu item
        # are hidden without a cookies file), so it runs during construction —
        # before first paint — rather than in the deferred startup work below.
        self.update_shorts_button_visibility()

        if not start_hidden:
            self.Show()
        self._start_ipc_server()
        # Defer non-essential startup work until after the window is shown and
        # the event loop is running, so the UI appears immediately instead of
        # blocking on browser-extension sync, URL association, home-feed loading
        # and the Discord presence connection. wx.CallAfter keeps it on the GUI
        # thread (invariant 1), so it runs once MainLoop starts painting.
        wx.CallAfter(self._deferred_startup)

    def _deferred_startup(self):
        if self._shutting_down.is_set():
            return
        self._startup_logic()
        try:
            from integrations import discord_presence

            discord_presence.init_presence()
            discord_presence.update_idle()
        except Exception:
            logger.debug(
                "Failed to initialize discord presence on startup", exc_info=True
            )
        if self.pending_launch_url and not self._shutting_down.is_set():
            self.handle_external_url(self.pending_launch_url)

    def _init_ui(self):
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self.panel = panel

        # Instruction label
        self.instruction = CustomLabel(
            panel,
            -1,
            _(
                "اضغط على مفتاح القوائم alt للوصول إلى خيارات البرنامج, أو تنقل بزر التاب للوصول سريعًا إلى أهم الخيارات المتاحة."
            ),
        )

        # Quick access buttons
        self.searchBtn = wx.Button(panel, -1, _("البحث في يوتيوب\tctrl+f"), name="tab")
        self.downloadBtn = wx.Button(
            panel, -1, _("التنزيل من خلال رابط\tctrl+d"), name="tab"
        )
        self.playBtn = wx.Button(
            panel, -1, _("تشغيل فيديو يوتيوب من خلال الرابط\tctrl+y"), name="tab"
        )
        self.shortsBtn = wx.Button(
            panel, -1, _("مشاهدة Shorts\tctrl+shift+s"), name="tab"
        )
        self.subscriptionsBtn = wx.Button(
            panel, -1, _("القنوات المشترك بها\tctrl+shift+u"), name="tab"
        )
        self.subscriptionsFeedBtn = wx.Button(
            panel, -1, _("Subscriptions feed\tctrl+shift+n"), name="tab"
        )
        self.favBtn = wx.Button(
            panel, -1, _("الفيديوهات المفضلة	ctrl+shift+f"), name="tab"
        )
        self.historyBtn = wx.Button(panel, -1, _("سجل المشاهدة\tctrl+h"), name="tab")
        self.musicBtn = wx.Button(panel, -1, _("يوتيوب ميوزك\tctrl+m"), name="tab")

        # Home feed
        self.home_feed_list = wx.ListBox(panel, -1, name="home_feed")
        self.home_feed_list.Hide()
        self.load_more_home_button = wx.Button(
            panel, -1, _("تحميل المزيد من الفيديوهات المقترحة")
        )
        self.load_more_home_button.Hide()

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        btnSizer = wx.BoxSizer(wx.VERTICAL)

        for child in panel.GetChildren():
            if child.Name == "tab":
                btnSizer.Add(child, 0, wx.EXPAND | wx.ALL, 5)

        self.subscriptionsFeedBtn.SetName(_("Subscriptions feed"))

        sizer.Add(self.instruction, 0, wx.ALL, 10)
        sizer.Add(self.home_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.load_more_home_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.AddStretchSpacer()
        sizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        panel.SetSizer(sizer)

        # Root frame sizer so a sibling YouTube Music panel can be flipped in
        # place (shown/hidden) without opening a new window. Built lazily.
        self._root_sizer = wx.BoxSizer(wx.VERTICAL)
        self._root_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(self._root_sizer)
        self.music_panel = None
        self._in_music_mode = False

    def _setup_menus(self):
        menuBar = wx.MenuBar()

        # Main Menu
        mainMenu = wx.Menu()
        self.searchItem = mainMenu.Append(-1, _("البحث في يوتيوب\tctrl+f"))
        self.downloadItem = mainMenu.Append(-1, _("التنزيل من خلال رابط\tctrl+d"))
        self.downloadQueueItem = mainMenu.Append(-1, _("Download queue\tCtrl+Shift+Q"))
        self.playItem = mainMenu.Append(
            -1, _("تشغيل فيديو يوتيوب من خلال الرابط\tctrl+y")
        )
        self.shortsItem = mainMenu.Append(-1, _("مشاهدة Shorts\tctrl+shift+s"))
        self.subscriptionsItem = mainMenu.Append(
            -1, _("القنوات المشترك بها\tctrl+shift+u")
        )
        self.subscriptionsFeedItem = mainMenu.Append(
            -1, _("Subscriptions feed\tctrl+shift+n")
        )
        self.favItem = mainMenu.Append(-1, _("الفيديوهات المفضلة	ctrl+shift+f"))
        self.historyItem = mainMenu.Append(-1, _("سجل المشاهدة\tctrl+h"))
        self.musicItem = mainMenu.Append(-1, _("يوتيوب ميوزك\tctrl+m"))
        self.openPathItem = mainMenu.Append(-1, _("فتح مجلد التنزيل\tctrl+p"))
        self.settingsItem = mainMenu.Append(-1, _("الإعدادات...\talt+s"))
        self.exitItem = mainMenu.Append(-1, _("خروج\tctrl+w"))

        menuBar.Append(mainMenu, _("القائمة الرئيسية"))

        # Tools Menu
        toolsMenu = wx.Menu()
        self.showYtdlpVer = toolsMenu.Append(-1, _("عرض إصدار واي تي دي إل بي"))
        self.updateYtdlp = toolsMenu.Append(
            -1, _("التحقق من وجود تحديث لـ واي تي دي إل بي")
        )
        self.showDenoVer = toolsMenu.Append(-1, _("عرض إصدار دينو"))
        self.updateDeno = toolsMenu.Append(-1, _("التحقق من وجود تحديث لـ دينو"))
        self.showYoutubeiVer = toolsMenu.Append(
            -1, _("عرض إصدار YouTube.js (Innertube)")
        )
        self.updateYoutubei = toolsMenu.Append(
            -1, _("التحقق من وجود تحديث لـ YouTube.js (Innertube)")
        )
        self.refreshYoutubeiCache = toolsMenu.Append(
            -1, _("تحديث ذاكرة YouTube.js (Innertube) المؤقتة")
        )
        self.showPotProviderVer = toolsMenu.Append(-1, _("عرض إصدار مولد رموز POT"))
        self.updatePotProvider = toolsMenu.Append(
            -1, _("التحقق من وجود تحديث لـ مولد رموز POT")
        )
        self.openBrowserExtensionFolder = toolsMenu.Append(
            -1, _("فتح مجلد إضافة المتصفح")
        )
        self.openLogFileItem = toolsMenu.Append(
            -1, _("فتح ملف السجلات (hexplayer.log)")
        )
        menuBar.Append(toolsMenu, _("قائمة الأدوات الخارجية"))

        # About Menu
        aboutMenu = wx.Menu()
        self.welcomeTourItem = aboutMenu.Append(-1, _("شاشة الترحيب وجولة الميزات..."))
        self.guideItem = aboutMenu.Append(-1, _("دليل المستخدم...\tf1"))
        self.checkUpdatesItem = aboutMenu.Append(-1, _("البحث عن التحديثات"))
        self.privacyPolicyItem = aboutMenu.Append(-1, _("سياسة الخصوصية"))
        self.aboutItem = aboutMenu.Append(-1, _("عن البرنامج..."))

        contactMenu = wx.Menu()
        self.emailItem = contactMenu.Append(-1, _("البريد الالكتروني..."))
        self.telegramItem = contactMenu.Append(-1, _("تلجرام..."))
        aboutMenu.AppendSubMenu(contactMenu, _("تواصل معي"))

        menuBar.Append(aboutMenu, _("حول"))
        self.SetMenuBar(menuBar)
        self.update_deno_tools_visibility()

        # Accelerator Table
        accel = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("F"), self.searchItem.GetId()),
                (wx.ACCEL_CTRL, ord("D"), self.downloadItem.GetId()),
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("Q"),
                    self.downloadQueueItem.GetId(),
                ),
                (wx.ACCEL_CTRL, ord("Y"), self.playItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("S"), self.shortsItem.GetId()),
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("U"),
                    self.subscriptionsItem.GetId(),
                ),
                (
                    wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                    ord("N"),
                    self.subscriptionsFeedItem.GetId(),
                ),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("F"), self.favItem.GetId()),
                (wx.ACCEL_CTRL, ord("H"), self.historyItem.GetId()),
                (wx.ACCEL_CTRL, ord("M"), self.musicItem.GetId()),
                (wx.ACCEL_CTRL, ord("P"), self.openPathItem.GetId()),
                (wx.ACCEL_ALT, ord("S"), self.settingsItem.GetId()),
                (wx.ACCEL_CTRL, ord("W"), self.exitItem.GetId()),
            ]
        )
        self.SetAcceleratorTable(accel)

    def _bind_events(self):
        self.clip_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_clip_timer, self.clip_timer)
        # Menu items
        self.Bind(wx.EVT_MENU, self.onSearch, self.searchItem)
        self.Bind(wx.EVT_MENU, self.onDownload, self.downloadItem)
        self.Bind(wx.EVT_MENU, self.onDownloadQueue, self.downloadQueueItem)
        self.Bind(wx.EVT_MENU, self.onPlay, self.playItem)
        self.Bind(wx.EVT_MENU, self.on_open_shorts, self.shortsItem)
        self.Bind(wx.EVT_MENU, self.on_open_subscriptions, self.subscriptionsItem)
        self.Bind(
            wx.EVT_MENU, self.on_open_subscriptions_feed, self.subscriptionsFeedItem
        )
        self.Bind(wx.EVT_MENU, self.onFavorite, self.favItem)
        self.Bind(wx.EVT_MENU, self.onHistory, self.historyItem)
        self.Bind(wx.EVT_MENU, self.onMusic, self.musicItem)
        self.Bind(wx.EVT_MENU, self.onOpenPath, self.openPathItem)
        self.Bind(wx.EVT_MENU, self.onSettings, self.settingsItem)
        self.Bind(wx.EVT_MENU, self.onExit, self.exitItem)

        self.Bind(wx.EVT_MENU, self.on_show_yt_dlp_version, self.showYtdlpVer)
        self.Bind(wx.EVT_MENU, self.on_update_yt_dlp, self.updateYtdlp)
        self.Bind(wx.EVT_MENU, self.on_show_deno_version, self.showDenoVer)
        self.Bind(wx.EVT_MENU, self.on_update_deno, self.updateDeno)
        self.Bind(wx.EVT_MENU, self.on_show_youtubei_version, self.showYoutubeiVer)
        self.Bind(wx.EVT_MENU, self.on_update_youtubei, self.updateYoutubei)
        self.Bind(
            wx.EVT_MENU,
            self.on_refresh_youtubei_cache,
            self.refreshYoutubeiCache,
        )
        self.Bind(
            wx.EVT_MENU,
            self.on_show_pot_provider_version,
            self.showPotProviderVer,
        )
        self.Bind(
            wx.EVT_MENU,
            self.on_update_pot_provider,
            self.updatePotProvider,
        )
        self.Bind(
            wx.EVT_MENU,
            self.onOpenBrowserExtensionFolder,
            self.openBrowserExtensionFolder,
        )
        self.Bind(wx.EVT_MENU, self.on_open_log_file, self.openLogFileItem)

        self.Bind(wx.EVT_MENU, self.onWelcomeTour, self.welcomeTourItem)
        self.Bind(wx.EVT_MENU, self.onGuide, self.guideItem)
        self.Bind(wx.EVT_MENU, self.onCheckForUpdates, self.checkUpdatesItem)
        self.Bind(wx.EVT_MENU, self.onPrivacyPolicy, self.privacyPolicyItem)
        self.Bind(wx.EVT_MENU, self.onAbout, self.aboutItem)
        self.Bind(
            wx.EVT_MENU,
            lambda e: webbrowser.open("mailto:altrhwnyashrf1@gmail.com"),
            self.emailItem,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda e: webbrowser.open("https://t.me/makhlwf"),
            self.telegramItem,
        )

        # Buttons
        self.searchBtn.Bind(wx.EVT_BUTTON, self.onSearch)
        self.downloadBtn.Bind(wx.EVT_BUTTON, self.onDownload)
        self.playBtn.Bind(wx.EVT_BUTTON, self.onPlay)
        self.shortsBtn.Bind(wx.EVT_BUTTON, self.on_open_shorts)
        self.subscriptionsBtn.Bind(wx.EVT_BUTTON, self.on_open_subscriptions)
        self.subscriptionsFeedBtn.Bind(wx.EVT_BUTTON, self.on_open_subscriptions_feed)
        self.favBtn.Bind(wx.EVT_BUTTON, self.onFavorite)
        self.historyBtn.Bind(wx.EVT_BUTTON, self.onHistory)
        self.musicBtn.Bind(wx.EVT_BUTTON, self.onMusic)
        self.Bind(wx.EVT_SHOW, self._on_frame_show)
        self.load_more_home_button.Bind(
            wx.EVT_BUTTON, lambda event: self.load_home_feed(True)
        )

        # List box
        self.home_feed_list.Bind(wx.EVT_LISTBOX, self.on_home_feed_list_box)
        self.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_home_feed_play(event, audio_mode=False),
            self.home_feed_list,
        )
        self.home_feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_home_feed_hook)

        # Frame events
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, self.onClose)

    def on_open_log_file(self, event=None):
        if not os.path.exists(paths.log_path):
            try:
                with open(paths.log_path, "w", encoding="utf-8") as f:
                    f.write("HexPlayer log initialized.\n")
            except Exception:
                pass
        try:
            if not wx.LaunchDefaultApplication(paths.log_path):
                utils.show_error(_("Unable to open the log file."), parent=self)
        except Exception as e:
            logger.error(f"Failed to open log file: {e}")

    def _startup_logic(self):
        try:
            browser_extension_manager.sync_browser_extension_files()
        except Exception as e:
            logger.error("Failed to sync browser extension files: %s", e)

        legacy_url_association = settings_handler.config_get("url_association")
        if (
            legacy_url_association
            or windows_url_association.is_legacy_http_url_handler_registered()
        ) and windows_url_association.cleanup_legacy_http_url_handler():
            settings_handler.config_set("url_association", False)
        if settings_handler.config_get("browser_integration"):
            windows_url_association.register_browser_integration()

        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            self.load_home_feed()

        autodetect = settings_handler.config_get("autodetect")
        bg_monitoring = settings_handler.config_get("background_monitoring")

        if bg_monitoring:
            utils.set_startup(True)
            if autodetect:
                self.detectFromClipboard(True)
            else:
                try:
                    self.last_clip_content = pyperclip.paste()
                except Exception:
                    pass
            self.clip_timer.Start(1500)
        else:
            utils.set_startup(False)
            self.detectFromClipboard(autodetect)

        if settings_handler.config_get("checkupdates"):
            threading.Thread(
                target=utils.check_for_updates,
                args=(True,),
                daemon=True,
            ).start()

    def is_app_active(self):
        if wx.GetActiveWindow() is not None:
            return True
        for win in wx.GetTopLevelWindows():
            if win.IsShown() and win.IsActive():
                return True
        return False

    def on_clip_timer(self, event):
        try:
            clip_content = pyperclip.paste()
        except Exception:
            return
        if clip_content != self.last_clip_content:
            self.last_clip_content = clip_content
            if self.is_app_active():
                return
            detected_url = utils.extract_supported_youtube_url(clip_content)
            if detected_url:
                from gui.auto_detect_dialog import AutoDetectDialog

                dlg = AutoDetectDialog(self, detected_url)
                utils.ensure_focus(dlg)
                dlg.ShowModal()

    def on_show_yt_dlp_version(self, event):
        version = utils.get_yt_dlp_version()
        if not version:
            utils.show_error(
                _("لم يتم العثور على مكتبة واي تي دي إل بي أو تعذر الحصول على إصدارها"),
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار واي تي دي إل بي"), parent=self)

    def on_show_deno_version(self, event):
        version = utils.get_deno_version()
        if not version:
            utils.show_error(
                _("لم يتم العثور على أداة دينو أو تعذر الحصول على إصدارها"),
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار دينو"), parent=self)

    def on_show_youtubei_version(self, event=None):
        version = utils.get_youtubei_version()
        if not version:
            wx.MessageBox(
                _("تعذر جلب إصدار YouTube.js (Innertube)"),
                _("خطأ"),
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار YouTube.js (Innertube)"), parent=self)

    def on_show_pot_provider_version(self, event):
        version = utils.get_pot_provider_version()
        if not version:
            wx.MessageBox(
                _("أداة مولد رموز POT غير مثبتة حالياً."),
                _("معلومات الإصدار"),
                parent=self,
            )
            return

        status = _("قيد التشغيل") if pot_service.is_healthy() else _("متوقف")
        wx.MessageBox(
            _("إصدار مولد رموز POT: {}\nحالة الخادم المحلي: {}").format(
                version, status
            ),
            _("معلومات الإصدار"),
            parent=self,
        )

    def load_home_feed(self, load_more=False):
        continuation = self.home_feed_continuation if load_more else None
        if self._shutting_down.is_set() or (load_more and not continuation):
            return
        cookies_path = settings_handler.config_get("cookiespath")
        if self._home_feed_request is not None:
            pending_cookies, _token = self._home_feed_request
            if pending_cookies == cookies_path:
                return
        token = object()
        self._home_feed_request = (cookies_path, token)
        # These checks may open dialogs. The worker receives the cookie path
        # that was checked here, so it does not consult changing UI settings.
        feature_name = _("عرض الخلاصة الرئيسية")
        ready = utils.ensure_deno_installed(
            parent=self, feature_name=feature_name
        ) and utils.ensure_cookies_configured(parent=self, feature_name=feature_name)
        if self._home_feed_request != (cookies_path, token):
            return
        if (
            not ready
            or self._shutting_down.is_set()
            or settings_handler.config_get("cookiespath") != cookies_path
        ):
            self._home_feed_request = None
            return

        if not load_more:
            self.home_feed_continuation = None
            self.home_feed_data = []
            self.home_feed_results = None
            self.scraper.set_results(None)
            self.home_feed_list.Set([_("جاري تحميل الاقتراحات... يرجى الانتظار")])
            self.home_feed_list.Show()
            self.load_more_home_button.Hide()
            self.Layout()

        def _load():
            try:
                data = utils.get_home_feed(continuation, cookies_path=cookies_path)
            except Exception:
                logger.exception("Failed to load home feed")
                data = None
            wx.CallAfter(self._finish_home_feed, cookies_path, token, data, load_more)

        # Run feed loading in a thread to keep UI responsive
        threading.Thread(target=_load, daemon=True).start()

    def _finish_home_feed(self, cookies_path, token, data, load_more):
        if self._home_feed_request != (cookies_path, token):
            return
        self._home_feed_request = None
        if (
            not self._shutting_down.is_set()
            and settings_handler.config_get("cookiespath") == cookies_path
        ):
            self._update_home_feed(data, load_more)

    def _update_home_feed(self, data, load_more=False):
        from youtube_browser.search_handler import SimpleResult

        if isinstance(data, dict) and data.get("error"):
            err_msg = data["error"]
            speak(err_msg, interrupt=True)
            wx.MessageBox(
                err_msg,
                _("تنبيه"),
                style=wx.OK | wx.ICON_WARNING,
                parent=self,
            )
        if load_more and (not isinstance(data, dict) or data.get("error")):
            return

        new_videos = data.get("videos", []) if isinstance(data, dict) else []
        self.home_feed_continuation = (
            data.get("continuation") if isinstance(data, dict) else None
        )

        old_count = len(self.home_feed_data)
        if load_more:
            self.home_feed_data.extend(new_videos)
        else:
            self.home_feed_data = new_videos
            self.home_feed_list.Clear()

        self.home_feed_results = SimpleResult(self.home_feed_data)
        self.home_feed_results.scraper = self.scraper
        self.scraper.set_results(self.home_feed_results)

        if not self.home_feed_data:
            titles = [
                _(
                    "لا توجد اقتراحات متاحة حاليًا في حسابك (قد يكون سجل المشاهدة متوقفًا في إعدادات YouTube)."
                )
            ]
            self.home_feed_list.Set(titles)
            self.home_feed_list.Show(True)
            self.load_more_home_button.Hide()
        else:
            titles = []
            for item in self.home_feed_data:
                if item.get("type") == "mix":
                    titles.append(
                        _("قائمة تشغيل مختلطة: {title}").format(title=item["title"])
                    )
                else:
                    titles.append(f"{item['title']} - {item['author']}")
            self.home_feed_list.Set(titles)
            self.home_feed_list.Show(True)
            self.load_more_home_button.Show(self.home_feed_continuation is not None)
        self.Layout()

        # Add items to scraper using the async loop. Mixes are skipped: their URL
        # carries a list=RD… id that would mis-resolve through get_playable_stream,
        # and a mix is opened via play_mix (which fetches its own items) instead.
        def _add_to_scraper():
            if not load_more:
                for i in range(min(10, self.home_feed_results.count)):
                    if self.home_feed_data[i].get("type") == "mix":
                        continue
                    self.scraper.add_item(i, priority=10)
            else:
                for i in range(old_count, self.home_feed_results.count):
                    if self.home_feed_data[i].get("type") == "mix":
                        continue
                    self.scraper.add_item(i, priority=10)

        _add_to_scraper()

    def on_home_feed_play(self, event, audio_mode=False):
        selection = self.home_feed_list.GetSelection()
        results = self.home_feed_results
        if results is None or not 0 <= selection < len(self.home_feed_data):
            return
        from media_player.media_gui import MediaGui, play_mix

        video_data = self.home_feed_data[selection]
        if video_data.get("type") == "mix":
            logger.info(
                "home feed: selected item is a mix (playlistId=%s seed=%s) -> play_mix",
                video_data.get("playlistId"),
                video_data.get("id"),
            )
            if (
                play_mix(
                    self,
                    video_data.get("playlistId"),
                    video_data.get("id"),
                    audio_mode=audio_mode,
                )
                is not None
            ):
                self.Hide()
            return
        url = video_data["url"]
        stream = results.get_stream(selection, audio_mode=audio_mode)
        if stream is None:
            if not utils.check_yt_dlp(self):
                return
            stream = LoadingDialog(
                self, _("جاري التشغيل"), utils.get_playable_stream, url, audio_mode
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        MediaGui(
            self,
            stream.title,
            stream,
            url,
            audio_mode=audio_mode,
            results=results,
        )
        self.Hide()

    def on_home_feed_list_box(self, event):
        n = self.home_feed_list.Selection
        if not 0 <= n < len(self.home_feed_data):
            return
        if self.home_feed_data[n].get("type") != "mix":
            self.scraper.add_item(n, priority=0)
        if n > 0 and n % 10 == 0:
            for i in range(n, min(n + 10, len(self.home_feed_data))):
                if self.home_feed_data[i].get("type") != "mix":
                    self.scraper.add_item(i, priority=10)

    def on_home_feed_hook(self, event):
        if event.KeyCode == wx.WXK_RETURN:
            self.on_home_feed_play(None, audio_mode=not event.ControlDown())
        else:
            event.Skip()

    def on_update_deno(self, event):
        utils.update_deno()

    def on_update_yt_dlp(self, event):
        utils.update_yt_dlp()

    def on_update_youtubei(self, event):
        utils.update_youtubei(parent=self)

    def on_refresh_youtubei_cache(self, event):
        utils.refresh_youtubei_cache(parent=self)

    def on_update_pot_provider(self, event):
        utils.update_pot_provider(parent=self)

    def onOpenBrowserExtensionFolder(self, event):
        try:
            extension_path = browser_extension_manager.sync_browser_extension_files()
        except Exception as e:
            logger.error("Failed to sync browser extension files: %s", e)
            extension_path = browser_extension_manager.get_user_extension_path()
        if not os.path.isdir(extension_path):
            utils.show_error(_("تعذر العثور على مجلد إضافة المتصفح"), parent=self)
            return
        if not wx.LaunchDefaultApplication(extension_path):
            utils.show_error(
                _("Unable to open the browser extension folder."), parent=self
            )

    def onPlay(self, event):
        from gui.link_dlg import LinkDlg
        from media_player.media_gui import MediaGui, play_mix

        linkDlg = LinkDlg(self)
        data = linkDlg.data
        if not data["link"]:
            return
        url = data["link"]
        audio_mode = data["audio"]
        if not utils.check_yt_dlp(self):
            return
        mix_id = utils.extract_mix_id(url)
        if mix_id:
            if (
                play_mix(
                    self, mix_id, utils.extract_video_id(url), audio_mode=audio_mode
                )
                is not None
            ):
                self.Hide()
            return
        stream = LoadingDialog(
            self, _("جاري التشغيل"), utils.get_playable_stream, url, audio_mode
        ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        MediaGui(self, stream.title, stream, url, audio_mode=audio_mode)
        self.Hide()

    def onDownload(self, event):
        from gui.download_dialog import show_download_window

        show_download_window(self)

    def onDownloadQueue(self, event):
        from gui.download_dialog import show_download_window

        show_download_window(self, focus_queue=True)

    def onSearch(self, event):
        from youtube_browser.browser import YoutubeBrowser

        YoutubeBrowser(self)

    def onHistory(self, event):
        from gui.history import HistoryDialog

        HistoryDialog(self)

    def _ensure_music_panel(self):
        if self.music_panel is None:
            from youtube_music.music_panel import YouTubeMusicPanel

            self.music_panel = YouTubeMusicPanel(self, self)
            self._root_sizer.Add(self.music_panel, 1, wx.EXPAND)
            self.music_panel.Hide()
        return self.music_panel

    def onMusic(self, event=None):
        self.open_music()

    def open_music(self):
        """Flip the UI in place from YouTube to YouTube Music (same window)."""
        if not settings_handler.config_get("youtube_music_enabled"):
            speak(_("يوتيوب ميوزك معطّل من الإعدادات"))
            return
        try:
            panel = self._ensure_music_panel()
        except Exception:
            logger.exception("Failed to open YouTube Music")
            speak(_("تعذر فتح يوتيوب ميوزك"))
            utils.show_error(_("تعذر فتح يوتيوب ميوزك."), parent=self)
            return
        self.Freeze()
        try:
            self.panel.Hide()
            panel.Show()
            self._root_sizer.Layout()
        finally:
            self.Thaw()
        self._in_music_mode = True
        speak(_("يوتيوب ميوزك"))
        panel.activate()

    def close_music(self):
        """Flip back from YouTube Music to the normal YouTube home screen."""
        self._in_music_mode = False
        if self.music_panel is not None:
            self.music_panel.Hide()
        self.panel.Show()
        self._root_sizer.Layout()
        try:
            self.musicBtn.SetFocus()
        except Exception:
            logger.debug("Could not focus music button after close", exc_info=True)
        speak(_("يوتيوب"))

    def _on_frame_show(self, event):
        """When the frame is reshown after the media player closes while in
        YouTube Music mode, re-assert the flip so the normal home never flashes
        and focus returns to the music list."""
        event.Skip()
        if (
            event.IsShown()
            and getattr(self, "_in_music_mode", False)
            and self.music_panel is not None
        ):
            wx.CallAfter(self._restore_music_after_show)

    def _restore_music_after_show(self):
        if not getattr(self, "_in_music_mode", False) or self.music_panel is None:
            return
        if self.panel.IsShown() or not self.music_panel.IsShown():
            self.Freeze()
            try:
                self.panel.Hide()
                self.music_panel.Show()
                self._root_sizer.Layout()
            finally:
                self.Thaw()
        self.music_panel.focus_list()

    def open_music_settings(self):
        """Open Settings (used when YouTube Music needs the user to sign in)."""
        from gui.settings_dialog import SettingsDialog

        try:
            SettingsDialog(self)
        except Exception:
            logger.exception("Failed to open settings from YouTube Music")

    def detectFromClipboard(self, config):
        if not config:
            return
        try:
            clip_content = pyperclip.paste()
        except Exception:
            return
        self.last_clip_content = clip_content
        detected_url = utils.extract_supported_youtube_url(clip_content)
        if detected_url:
            from gui.auto_detect_dialog import AutoDetectDialog

            AutoDetectDialog(self, detected_url).ShowModal()

    def handle_external_url(self, url):
        url = utils.extract_supported_youtube_url(url)
        if not url:
            return
        if not self.IsShown():
            self.Show()
        self.Raise()
        from gui.auto_detect_dialog import AutoDetectDialog

        dlg = AutoDetectDialog(self, url, source="external")
        utils.ensure_focus(dlg)
        dlg.ShowModal()

    def onSettings(self, event):
        from gui.settings_dialog import SettingsDialog

        previous_cookies_path = settings_handler.config_get("cookiespath")
        SettingsDialog(self)
        if settings_handler.config_get("background_monitoring"):
            utils.set_startup(True)
            if not self.clip_timer.IsRunning():
                try:
                    self.last_clip_content = pyperclip.paste()
                except Exception:
                    pass
                self.clip_timer.Start(1500)
        else:
            utils.set_startup(False)
            if self.clip_timer.IsRunning():
                self.clip_timer.Stop()

        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            if (
                cookies_path != previous_cookies_path
                or not self.home_feed_list.IsShown()
                or not self.home_feed_data
            ):
                self.load_home_feed()
        else:
            self._home_feed_request = None
            self.home_feed_list.Hide()
            self.load_more_home_button.Hide()
            self.Layout()
        self.update_shorts_button_visibility()
        self.update_deno_tools_visibility()

    def update_deno_tools_visibility(self):
        use_deno = bool(settings_handler.config_get("use_deno_backend"))
        if hasattr(self, "showDenoVer"):
            self.showDenoVer.Enable(use_deno)
        if hasattr(self, "updateDeno"):
            self.updateDeno.Enable(use_deno)
        if hasattr(self, "refreshYoutubeiCache"):
            self.refreshYoutubeiCache.Enable(use_deno)

    def update_shorts_button_visibility(self):
        has_cookies = utils.has_cookies_file()
        if hasattr(self, "shortsBtn"):
            self.shortsBtn.Show(has_cookies)
        if hasattr(self, "shortsItem"):
            self.shortsItem.Enable(has_cookies)
        if hasattr(self, "subscriptionsBtn"):
            self.subscriptionsBtn.Show(has_cookies)
        if hasattr(self, "subscriptionsItem"):
            self.subscriptionsItem.Enable(has_cookies)
        if hasattr(self, "subscriptionsFeedBtn"):
            self.subscriptionsFeedBtn.Show(has_cookies)
        if hasattr(self, "subscriptionsFeedItem"):
            self.subscriptionsFeedItem.Enable(has_cookies)
        if hasattr(self, "panel"):
            self.panel.Layout()

    def on_open_subscriptions_feed(self, event=None):
        from gui.subscriptions_feed import SubscriptionsFeed

        if not utils.has_cookies_file():
            message = _(
                "Import YouTube cookies in Settings to view your subscriptions feed."
            )
            speak(message, interrupt=True)
            utils.show_error(message, parent=self)
            return
        # Dependency prompts belong on the GUI thread, never in the feed worker.
        if not utils.ensure_deno_installed(
            parent=self, feature_name=_("Subscriptions feed")
        ):
            return
        SubscriptionsFeed(self, return_focus=self.subscriptionsFeedBtn)

    def on_open_subscriptions(self, event=None):
        from gui.subscriptions_dialog import SubscriptionsDialog

        if not utils.has_cookies_file():
            utils.show_error(
                _("يجب تحديد ملف الكوكيز من الإعدادات لعرض القنوات المشترك بها."),
                parent=self,
            )
            return

        SubscriptionsDialog(self)

    def on_open_shorts(self, event=None):
        from media_player.media_gui import MediaGui

        if not utils.has_cookies_file():
            utils.show_error(
                _("يجب تحديد ملف الكوكيز من الإعدادات لاستخدام ميزة Shorts."),
                parent=self,
            )
            return

        loading = LoadingDialog(
            self,
            _("جاري تحميل فيديوهات Shorts المقترحة..."),
            utils.get_shorts_feed,
        )
        shorts = loading.res
        if not shorts:
            utils.show_error(
                _(
                    "تعذر تحميل فيديوهات Shorts. يرجى التحقق من ملف الكوكيز والاتصال بالإنترنت."
                ),
                parent=self,
            )
            return

        first_short = shorts[0]
        first_url = first_short["url"]
        first_title = first_short["title"]

        stream = LoadingDialog(
            self,
            _("جاري جلب رابط التشغيل..."),
            utils.get_playable_stream,
            first_url,
            audio_mode=False,
        ).res

        if not stream:
            utils.show_error(_("تعذر استخراج رابط تشغيل الفيديو."), parent=self)
            return

        MediaGui(
            self,
            title=first_title,
            stream=stream,
            url=first_url,
            can_download=True,
            results=shorts,
            audio_mode=False,
            shorts_mode=True,
        )
        self.Hide()

    def onFavorite(self, event):
        from gui.favorites import Favorites

        Favorites(self)
        self.Hide()

    def onOpenPath(self, event):
        path = settings_handler.config_get("path")
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if not wx.LaunchDefaultApplication(path):
            utils.show_error(_("Unable to open the download folder."), parent=self)

    def onHook(self, event):
        if event.KeyCode == wx.WXK_F1:
            self.onGuide(None)
        else:
            event.Skip()

    def onShow(self, event):
        if not event.IsShown() or self._shutting_down.is_set():
            event.Skip()
            return
        if not self.checked:
            if not settings_handler.config_get("welcome_completed"):
                wx.CallAfter(self.show_welcome_screen)
            else:
                # Deferred off the synchronous Show() path so dependency probing
                # (which can lazily import yt-dlp) never blocks the first paint.
                wx.CallAfter(self.startup_dependency_checks)
            self.checked = True
        self.instruction.SetFocus()
        event.Skip()

    def show_welcome_screen(self):
        if self._shutting_down.is_set():
            return
        from gui.welcome_dialog import WelcomeDialog

        dlg = WelcomeDialog(self)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
            if hasattr(self, "instruction") and self.instruction:
                self.instruction.SetFocus()

    def onWelcomeTour(self, event=None):
        self.show_welcome_screen()

    def startup_dependency_checks(self):
        if self._shutting_down.is_set():
            return
        if utils.check_yt_dlp(self) and utils.check_deno(self):
            utils.ensure_js_dependencies()
        if self._shutting_down.is_set():
            return
        if pot_service.is_installed():
            threading.Thread(
                target=self._start_installed_pot_provider, daemon=True
            ).start()
        else:
            utils.check_pot_provider(self)

    def _start_installed_pot_provider(self):
        if self._shutting_down.is_set():
            return
        try:
            pot_service.ensure_started()
        except Exception:
            logger.exception("Failed to prepare the POT provider at startup")
        finally:
            if self._shutting_down.is_set():
                pot_service.stop()

    def onGuide(self, event):
        from gui.doc_handler import documentation_get
        from gui.text_viewer import Viewer

        content = documentation_get()
        if content:
            Viewer(self, _("دليل استخدام برنامج HexPlayer"), content).ShowModal()

    def onPrivacyPolicy(self, event):
        from gui.text_viewer import Viewer

        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "PRIVACY_POLICY.md"
        )
        if not os.path.exists(path):
            # Try same directory as script (for bundled)
            path = os.path.join(os.path.dirname(__file__), "PRIVACY_POLICY.md")

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            Viewer(self, _("سياسة الخصوصية"), content).ShowModal()
        else:
            utils.show_error(_("تعذر العثور على ملف سياسة الخصوصية"), parent=self)

    def onCheckForUpdates(self, event):
        LoadingDialog(
            self, _("جاري البحث عن التحديثات. يرجى الانتظار"), utils.check_for_updates
        )
        self.instruction.SetFocus()

    def onAbout(self, event):
        about = f"""{_("اسم البرنامج")}: {application.name}.
{_("الإصدار")}: {application.version}.
{_("طُوِر بواسطة")}: {application.author}.
{_("الوصف: ")}{_(application.description)}."""
        wx.MessageBox(about, _("حول"), parent=self)

    def onExit(self, event=None):
        if self._shutting_down.is_set():
            return
        self._shutting_down.set()
        self.clip_timer.Stop()
        self.tray_icon.Destroy()
        database.disconnect()
        settings_handler.save_settings()
        deno_service.stop()
        pot_service.stop()
        stop_async_loop()
        try:
            from integrations import discord_presence

            discord_presence.close_presence()
        except Exception:
            pass
        self.Destroy()
        wx.Exit()

    def onClose(self, event):
        if event.CanVeto() and settings_handler.config_get("background_monitoring"):
            event.Veto()
            self.Hide()
        else:
            self.onExit()

    def _start_ipc_server(self):
        start_ipc_server(
            self._shutting_down,
            lambda data: wx.CallAfter(self._handle_ipc_message, data),
        )

    def _handle_ipc_message(self, data):
        if self._shutting_down.is_set():
            return
        try:
            message = {"action": "show"} if data == b"SHOW" else json.loads(data)
        except ValueError, RecursionError:
            return
        if not isinstance(message, dict):
            return
        action = message.get("action")
        if action == "show":
            self.tray_icon.on_show(None)
        elif action == "open_url" and isinstance(url := message.get("url"), str):
            self.handle_external_url(url)
        elif action == "cookies_updated":
            self.update_shorts_button_visibility()
