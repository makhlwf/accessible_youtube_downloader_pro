# ruff: noqa: E402
import os
import socket
import sys

# Early setup for VLC and other DLLs
vlc_path = os.path.dirname(__file__)
if sys.platform == "win32":
    os.add_dll_directory(vlc_path)
os.environ["VLC_PLUGIN_PATH"] = os.path.join(vlc_path, "plugins")

import threading
import webbrowser
import subprocess
import logging
import asyncio
import wx
import pyperclip
import settings_handler
from theme_handler import apply_theme
from language_handler import init_translation, codes, _
import application
import database
import utils
from async_utils import start_async_loop, stop_async_loop
from gui.activity_dialog import LoadingDialog
from gui.auto_detect_dialog import AutoDetectDialog
from gui.download_dialog import DownloadDialog
from gui.link_dlg import LinkDlg
from gui.settings_dialog import SettingsDialog
from gui.text_viewer import Viewer
from gui.custom_controls import CustomLabel
from gui.favorites import Favorites
from gui.history import HistoryDialog
from doc_handler import documentation_get
from media_player.media_gui import MediaGui
from gui.tray_icon import TaskBarIcon
from youtube_browser.browser import YoutubeBrowser
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HomeScreen(wx.Frame):
    def __init__(self, start_hidden=False):
        wx.Frame.__init__(self, parent=None, title=application.name)
        settings_handler.config_initialization()
        init_translation("HexPlayer")

        self.checked = False
        self.home_feed_data = []
        self.home_feed_results = None
        self.scraper = Scraper()
        self.home_feed_continuation = None
        self.last_clip_content = ""
        self.tray_icon = TaskBarIcon(self)

        self._init_ui()
        apply_theme(self)
        self._setup_menus()
        self._bind_events()

        if not start_hidden:
            self.Show()
        self._start_ipc_server()
        self._startup_logic()

    def _init_ui(self):
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        panel = wx.Panel(self)
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
        self.favBtn = wx.Button(
            panel, -1, _("الفيديوهات المفضلة	ctrl+shift+f"), name="tab"
        )
        self.historyBtn = wx.Button(panel, -1, _("سجل المشاهدة\tctrl+h"), name="tab")
        self.historyBtn.Hide()

        # Home feed
        self.home_feed_list = wx.ListBox(panel, -1, name="home_feed")
        self.home_feed_list.Hide()
        self.load_more_home_button = wx.Button(
            panel, -1, _("تحميل المزيد من الفيديوهات المقترحة")
        )
        self.load_more_home_button.Hide()

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        btnSizer = wx.BoxSizer(wx.HORIZONTAL)

        for child in panel.GetChildren():
            if child.Name == "tab":
                btnSizer.Add(child, 1, wx.EXPAND | wx.ALL, 5)

        sizer.Add(self.instruction, 0, wx.ALL, 10)
        sizer.Add(self.home_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.load_more_home_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.AddStretchSpacer()
        sizer.Add(btnSizer, 0, wx.EXPAND)

        panel.SetSizer(sizer)

    def _setup_menus(self):
        menuBar = wx.MenuBar()

        # Main Menu
        mainMenu = wx.Menu()
        self.searchItem = mainMenu.Append(-1, _("البحث في يوتيوب\tctrl+f"))
        self.downloadItem = mainMenu.Append(-1, _("التنزيل من خلال رابط\tctrl+d"))
        self.playItem = mainMenu.Append(
            -1, _("تشغيل فيديو يوتيوب من خلال الرابط\tctrl+y")
        )
        self.favItem = mainMenu.Append(-1, _("الفيديوهات المفضلة	ctrl+shift+f"))
        self.historyItem = mainMenu.Append(-1, _("سجل المشاهدة\tctrl+h"))
        self.historyItem.Enable(False)
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
        menuBar.Append(toolsMenu, _("قائمة الأدوات الخارجية"))

        # About Menu
        aboutMenu = wx.Menu()
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

        # Accelerator Table
        accel = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("F"), self.searchItem.GetId()),
                (wx.ACCEL_CTRL, ord("D"), self.downloadItem.GetId()),
                (wx.ACCEL_CTRL, ord("Y"), self.playItem.GetId()),
                (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("F"), self.favItem.GetId()),
                (wx.ACCEL_CTRL, ord("H"), self.historyItem.GetId()),
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
        self.Bind(wx.EVT_MENU, self.onPlay, self.playItem)
        self.Bind(wx.EVT_MENU, self.onFavorite, self.favItem)
        self.Bind(wx.EVT_MENU, self.onHistory, self.historyItem)
        self.Bind(wx.EVT_MENU, self.onOpenPath, self.openPathItem)
        self.Bind(wx.EVT_MENU, self.onSettings, self.settingsItem)
        self.Bind(wx.EVT_MENU, self.onExit, self.exitItem)

        self.Bind(wx.EVT_MENU, self.on_show_yt_dlp_version, self.showYtdlpVer)
        self.Bind(wx.EVT_MENU, self.on_update_yt_dlp, self.updateYtdlp)
        self.Bind(wx.EVT_MENU, self.on_show_deno_version, self.showDenoVer)
        self.Bind(wx.EVT_MENU, self.on_update_deno, self.updateDeno)

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
        self.favBtn.Bind(wx.EVT_BUTTON, self.onFavorite)
        self.historyBtn.Bind(wx.EVT_BUTTON, self.onHistory)
        self.load_more_home_button.Bind(
            wx.EVT_BUTTON, lambda e: self.load_home_feed(True)
        )

        # List box
        self.home_feed_list.Bind(wx.EVT_LISTBOX, self.on_home_feed_list_box)
        self.home_feed_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda e: self.on_home_feed_play(None, audio_mode=True),
        )
        self.home_feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_home_feed_hook)

        # Frame events
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, self.onClose)

    def _startup_logic(self):
        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            self.historyBtn.Show()
            self.historyItem.Enable(True)
            self.load_home_feed()

        if settings_handler.config_get("background_monitoring"):
            utils.set_startup(True)
            self.clip_timer.Start(1500)
        else:
            utils.set_startup(False)
            self.detectFromClipboard(settings_handler.config_get("autodetect"))

        if settings_handler.config_get("checkupdates"):
            asyncio.run_coroutine_threadsafe(
                asyncio.to_thread(utils.check_for_updates, True),
                asyncio.get_event_loop(),
            )

    def on_clip_timer(self, event):
        try:
            clip_content = pyperclip.paste()
        except Exception:
            return
        if clip_content != self.last_clip_content:
            self.last_clip_content = clip_content
            if utils.youtube_regexp(clip_content):
                dlg = AutoDetectDialog(self, clip_content)
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

    def load_home_feed(self, load_more=False):
        if not load_more:
            self.home_feed_list.Set([_("جاري تحميل الاقتراحات... يرجى الانتظار")])
            self.home_feed_list.Show()
            self.Layout()

        continuation = self.home_feed_continuation if load_more else None

        def _load():
            try:
                data = utils.get_home_feed(continuation)
                wx.CallAfter(self._update_home_feed, data, load_more)
            except Exception as e:
                logger.error(f"Failed to load home feed: {e}")

        # Run feed loading in a thread to keep UI responsive
        threading.Thread(target=_load, daemon=True).start()

    def _update_home_feed(self, data, load_more=False):
        new_videos = data.get("videos", [])
        self.home_feed_continuation = data.get("continuation")

        old_count = len(self.home_feed_data)
        if load_more:
            self.home_feed_data.extend(new_videos)
        else:
            self.home_feed_data = new_videos
            self.home_feed_list.Clear()

        self.home_feed_results = SimpleResult(self.home_feed_data)
        self.home_feed_results.scraper = self.scraper
        self.scraper.set_results(self.home_feed_results)

        titles = [f"{item['title']} - {item['author']}" for item in self.home_feed_data]
        self.home_feed_list.Set(titles)

        show_list = len(self.home_feed_data) > 0
        self.home_feed_list.Show(show_list)
        self.load_more_home_button.Show(
            show_list and self.home_feed_continuation is not None
        )
        self.Layout()

        # Add items to scraper using the async loop
        def _add_to_scraper():
            loop = asyncio.get_event_loop()
            if not load_more:
                for i in range(min(10, self.home_feed_results.count)):
                    asyncio.run_coroutine_threadsafe(
                        self.scraper.add_item(i, priority=10), loop
                    )
            else:
                for i in range(old_count, self.home_feed_results.count):
                    asyncio.run_coroutine_threadsafe(
                        self.scraper.add_item(i, priority=10), loop
                    )

        _add_to_scraper()

    def on_home_feed_play(self, event, audio_mode=False):
        selection = self.home_feed_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        video_data = self.home_feed_data[selection]
        url = video_data["url"]
        stream = self.home_feed_results.get_stream(selection)
        if stream is None:
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
            results=self.home_feed_results,
        )
        self.Hide()

    def on_home_feed_list_box(self, event):
        n = self.home_feed_list.Selection
        if n != wx.NOT_FOUND:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self.scraper.add_item(n, priority=0), loop)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.home_feed_results.count)):
                    asyncio.run_coroutine_threadsafe(
                        self.scraper.add_item(i, priority=10), loop
                    )

    def on_home_feed_hook(self, event):
        if event.KeyCode == wx.WXK_RETURN:
            self.on_home_feed_play(None, audio_mode=not event.ControlDown())
        else:
            event.Skip()

    def on_update_deno(self, event):
        utils.update_deno()

    def on_update_yt_dlp(self, event):
        utils.update_yt_dlp()

    def onPlay(self, event):
        linkDlg = LinkDlg(self)
        data = linkDlg.data
        if not data["link"]:
            return
        url = data["link"]
        audio_mode = data["audio"]
        stream = LoadingDialog(
            self, _("جاري التشغيل"), utils.get_playable_stream, url, audio_mode
        ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        MediaGui(self, stream.title, stream, url, audio_mode=audio_mode)
        self.Hide()

    def onDownload(self, event):
        DownloadDialog(self).Show()

    def onSearch(self, event):
        YoutubeBrowser(self)

    def onHistory(self, event):
        HistoryDialog(self)

    def detectFromClipboard(self, config):
        if not config:
            return
        clip_content = pyperclip.paste()
        if utils.youtube_regexp(clip_content):
            AutoDetectDialog(self, clip_content).ShowModal()

    def onSettings(self, event):
        SettingsDialog(self)
        if settings_handler.config_get("background_monitoring"):
            utils.set_startup(True)
            if not self.clip_timer.IsRunning():
                self.clip_timer.Start(1500)
        else:
            utils.set_startup(False)
            if self.clip_timer.IsRunning():
                self.clip_timer.Stop()

        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            if not self.home_feed_list.IsShown() or not self.home_feed_data:
                self.load_home_feed()
        else:
            self.home_feed_list.Hide()
            self.load_more_home_button.Hide()
            self.Layout()

    def onFavorite(self, event):
        Favorites(self)
        self.Hide()

    def onOpenPath(self, event):
        path = settings_handler.config_get("path")
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.call(["xdg-open", path])

    def onHook(self, event):
        if event.KeyCode == wx.WXK_F1:
            self.onGuide(None)
        else:
            event.Skip()

    def onShow(self, event):
        if not self.checked:
            asyncio.run_coroutine_threadsafe(
                self.async_startup_checks(), asyncio.get_event_loop()
            )
            self.checked = True
        self.instruction.SetFocus()
        event.Skip()

    async def async_startup_checks(self):
        # Move these to thread since they might show dialogs (which must be on main thread via CallAfter)
        def _checks():
            if utils.check_yt_dlp(self):
                if utils.check_deno(self):
                    utils.ensure_js_dependencies()

        await asyncio.to_thread(_checks)

    def onGuide(self, event):
        content = documentation_get()
        if content:
            Viewer(self, _("دليل استخدام برنامج HexPlayer"), content).ShowModal()

    def onPrivacyPolicy(self, event):
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
        self.clip_timer.Stop()
        self.tray_icon.Destroy()
        database.disconnect()
        settings_handler.save_settings()
        stop_async_loop()
        self.Destroy()
        wx.Exit()

    def onClose(self, event):
        if event.CanVeto() and settings_handler.config_get("background_monitoring"):
            event.Veto()
            self.Hide()
        else:
            self.onExit()

    def _start_ipc_server(self):
        def listen():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", 57280))
                s.listen(1)
                while True:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data == b"SHOW":
                            wx.CallAfter(self.tray_icon.on_show, None)
            except Exception:
                pass

        threading.Thread(target=listen, daemon=True).start()


if __name__ == "__main__":
    app = wx.App()

    # Single Instance Checker - run very early
    name = f"{application.name}-{wx.GetUserId()}"
    checker = wx.SingleInstanceChecker(name)
    if checker.IsAnotherRunning():
        if "--background" not in sys.argv:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("127.0.0.1", 57280))
                s.sendall(b"SHOW")
                s.close()
            except Exception:
                wx.MessageBox(
                    _("البرنامج قيد التشغيل بالفعل."),
                    _("تنبيه"),
                    style=wx.ICON_INFORMATION,
                )
        sys.exit()

    # Start the async loop early
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    threading.Thread(target=start_async_loop, daemon=True).start()

    lang_id = codes.get(settings_handler.config_get("lang"), wx.LANGUAGE_ARABIC)
    locale = wx.Locale(lang_id)

    start_hidden = "--background" in sys.argv
    home_screen = HomeScreen(start_hidden=start_hidden)
    # Start scraper workers now that loop is active
    asyncio.run_coroutine_threadsafe(
        asyncio.to_thread(home_screen.scraper.start_workers), loop
    )
    app.MainLoop()
