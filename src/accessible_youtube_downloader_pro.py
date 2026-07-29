import json
import os
import socket
import struct
import sys

# Early setup for MPV and other DLLs
from runtime_dlls import configure_dll_search_path

configure_dll_search_path()

import logging
import subprocess
import threading
import webbrowser

import pyperclip
import wx

import application
import browser_extension_manager
import database
import settings_handler
import utils
import windows_url_association
from async_utils import start_async_loop, stop_async_loop
from doc_handler import documentation_get
from gui.activity_dialog import LoadingDialog
from gui.auto_detect_dialog import AutoDetectDialog
from gui.custom_controls import CustomLabel
from gui.download_dialog import DownloadDialog
from gui.favorites import Favorites
from gui.history import HistoryDialog
from gui.link_dlg import LinkDlg
from gui.settings_dialog import SettingsDialog
from gui.text_viewer import Viewer
from gui.tray_icon import TaskBarIcon
from language_handler import _, codes, init_translation
from media_player.media_gui import MediaGui
from theme_handler import apply_theme
from youtube_browser.browser import YoutubeBrowser
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
IPC_HOST = "127.0.0.1"
IPC_PORT = 57280


def get_launch_url(argv):
    for arg in argv[1:]:
        if arg.startswith("--"):
            continue
        url = utils.extract_launch_youtube_url(arg)
        if url:
            return url
    return ""


def send_ipc_message(action, url=""):
    payload = json.dumps({"action": action, "url": url}).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        s.connect((IPC_HOST, IPC_PORT))
        s.sendall(payload)


def is_native_messaging_invocation(argv):
    return "--native-messaging-host" in argv or any(
        arg.startswith("chrome-extension://") for arg in argv[1:]
    )


def read_native_message(stdin=None):
    stdin = stdin or sys.stdin.buffer
    raw_length = stdin.read(4)
    if len(raw_length) == 0:
        return None
    if len(raw_length) != 4:
        raise ValueError("Invalid native message length header")
    message_length = struct.unpack("<I", raw_length)[0]
    if message_length > 1024 * 1024:
        raise ValueError("Native message is too large")
    data = stdin.read(message_length)
    if len(data) != message_length:
        raise ValueError("Incomplete native message")
    return json.loads(data.decode("utf-8"))


def write_native_message(message, stdout=None):
    stdout = stdout or sys.stdout.buffer
    data = json.dumps(message).encode("utf-8")
    stdout.write(struct.pack("<I", len(data)))
    stdout.write(data)
    stdout.flush()


def start_detached_process(command):
    kwargs = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(command, **kwargs)


def launch_or_forward_external_url(url):
    url = utils.extract_launch_youtube_url(url)
    if not url:
        return False

    try:
        send_ipc_message("open_url", url)
        return True
    except Exception:
        pass

    try:
        if getattr(sys, "frozen", False):
            start_detached_process([sys.executable, url])
        else:
            script_path = os.path.abspath(sys.modules["__main__"].__file__)
            start_detached_process([sys.executable, script_path, url])
        return True
    except Exception as e:
        logger.error("Failed to launch HexPlayer from native host: %s", e)
        return False


def native_messaging_main():
    try:
        message = read_native_message()
        if not isinstance(message, dict):
            write_native_message({"ok": False, "error": "Invalid message"})
            return 1
        if message.get("type") != "open":
            write_native_message({"ok": False, "error": "Unsupported message type"})
            return 1

        url = message.get("url", "")
        opened = launch_or_forward_external_url(url)
        write_native_message({"ok": opened})
        return 0 if opened else 1
    except Exception as e:
        try:
            write_native_message({"ok": False, "error": str(e)})
        except Exception:
            pass
        return 1


class HomeScreen(wx.Frame):
    def __init__(self, start_hidden=False, launch_url=""):
        wx.Frame.__init__(self, parent=None, title=application.name)
        settings_handler.config_initialization()
        init_translation("HexPlayer")

        self.checked = False
        self.home_feed_data = []
        self.home_feed_results = None
        self.scraper = Scraper()
        self.home_feed_continuation = None
        self.last_clip_content = ""
        self.pending_launch_url = launch_url
        self.tray_icon = TaskBarIcon(self)

        self._init_ui()
        apply_theme(self)
        self._setup_menus()
        self._bind_events()

        if not start_hidden:
            self.Show()
        self._start_ipc_server()
        self._startup_logic()
        if self.pending_launch_url:
            wx.CallAfter(self.handle_external_url, self.pending_launch_url)

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

        sizer.Add(self.instruction, 0, wx.ALL, 10)
        sizer.Add(self.home_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.load_more_home_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.AddStretchSpacer()
        sizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

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
        self.openBrowserExtensionFolder = toolsMenu.Append(
            -1, _("فتح مجلد إضافة المتصفح")
        )
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
        self.Bind(wx.EVT_MENU, self.on_show_youtubei_version, self.showYoutubeiVer)
        self.Bind(wx.EVT_MENU, self.on_update_youtubei, self.updateYoutubei)
        self.Bind(
            wx.EVT_MENU,
            self.on_refresh_youtubei_cache,
            self.refreshYoutubeiCache,
        )
        self.Bind(
            wx.EVT_MENU,
            self.onOpenBrowserExtensionFolder,
            self.openBrowserExtensionFolder,
        )

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
        try:
            browser_extension_manager.sync_browser_extension_files()
        except Exception as e:
            logger.error("Failed to sync browser extension files: %s", e)

        legacy_url_association = settings_handler.config_get("url_association")
        if (
            legacy_url_association
            or windows_url_association.is_legacy_http_url_handler_registered()
        ):
            if windows_url_association.cleanup_legacy_http_url_handler():
                settings_handler.config_set("url_association", False)
        if settings_handler.config_get("browser_integration"):
            windows_url_association.register_browser_integration()

        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            self.load_home_feed()

        if settings_handler.config_get("background_monitoring"):
            utils.set_startup(True)
            self.clip_timer.Start(1500)
        else:
            utils.set_startup(False)
            self.detectFromClipboard(settings_handler.config_get("autodetect"))

        if settings_handler.config_get("checkupdates"):
            threading.Thread(
                target=utils.check_for_updates,
                args=(True,),
                daemon=True,
            ).start()

    def on_clip_timer(self, event):
        try:
            clip_content = pyperclip.paste()
        except Exception:
            return
        if clip_content != self.last_clip_content:
            self.last_clip_content = clip_content
            detected_url = utils.extract_supported_youtube_url(clip_content)
            if detected_url:
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

    def on_show_youtubei_version(self, event):
        version = utils.get_youtubei_version()
        if not version:
            utils.show_error(
                _(
                    "لم يتم العثور على مكتبة YouTube.js (Innertube) أو تعذر الحصول على إصدارها"
                ),
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار YouTube.js (Innertube)"), parent=self)

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
            if not load_more:
                for i in range(min(10, self.home_feed_results.count)):
                    self.scraper.add_item(i, priority=10)
            else:
                for i in range(old_count, self.home_feed_results.count):
                    self.scraper.add_item(i, priority=10)

        _add_to_scraper()

    def on_home_feed_play(self, event, audio_mode=False):
        selection = self.home_feed_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        video_data = self.home_feed_data[selection]
        url = video_data["url"]
        stream = self.home_feed_results.get_stream(selection, audio_mode=audio_mode)
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
            results=self.home_feed_results,
        )
        self.Hide()

    def on_home_feed_list_box(self, event):
        n = self.home_feed_list.Selection
        if n != wx.NOT_FOUND:
            self.scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.home_feed_results.count)):
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

    def onOpenBrowserExtensionFolder(self, event):
        try:
            extension_path = browser_extension_manager.sync_browser_extension_files()
        except Exception as e:
            logger.error("Failed to sync browser extension files: %s", e)
            extension_path = browser_extension_manager.get_user_extension_path()
        if not os.path.isdir(extension_path):
            utils.show_error(_("تعذر العثور على مجلد إضافة المتصفح"), parent=self)
            return
        if sys.platform == "win32":
            os.startfile(extension_path)
        else:
            subprocess.call(["xdg-open", extension_path])

    def onPlay(self, event):
        linkDlg = LinkDlg(self)
        data = linkDlg.data
        if not data["link"]:
            return
        url = data["link"]
        audio_mode = data["audio"]
        if not utils.check_yt_dlp(self):
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
        DownloadDialog(self).Show()

    def onSearch(self, event):
        YoutubeBrowser(self)

    def onHistory(self, event):
        HistoryDialog(self)

    def detectFromClipboard(self, config):
        if not config:
            return
        clip_content = pyperclip.paste()
        detected_url = utils.extract_supported_youtube_url(clip_content)
        if detected_url:
            AutoDetectDialog(self, detected_url).ShowModal()

    def handle_external_url(self, url):
        url = utils.extract_supported_youtube_url(url)
        if not url:
            return
        if not self.IsShown():
            self.Show()
        self.Raise()
        dlg = AutoDetectDialog(self, url, source="external")
        utils.ensure_focus(dlg)
        dlg.ShowModal()

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
            self.startup_dependency_checks()
            self.checked = True
        self.instruction.SetFocus()
        event.Skip()

    def startup_dependency_checks(self):
        if utils.check_yt_dlp(self) and utils.check_deno(self):
            utils.ensure_js_dependencies()

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
        def handle_message(data):
            try:
                message = json.loads(data.decode("utf-8"))
            except Exception:
                if data == b"SHOW":
                    wx.CallAfter(self.tray_icon.on_show, None)
                return

            action = message.get("action")
            if action == "show":
                wx.CallAfter(self.tray_icon.on_show, None)
            elif action == "open_url":
                wx.CallAfter(self.handle_external_url, message.get("url", ""))

        def listen():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind((IPC_HOST, IPC_PORT))
                s.listen(1)
                while True:
                    conn, addr = s.accept()
                    with conn:
                        chunks = []
                        while True:
                            chunk = conn.recv(4096)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        if chunks:
                            handle_message(b"".join(chunks))
            except Exception:
                pass

        threading.Thread(target=listen, daemon=True).start()


if __name__ == "__main__":
    if is_native_messaging_invocation(sys.argv):
        sys.exit(native_messaging_main())

    app = wx.App()
    launch_url = get_launch_url(sys.argv)

    # Single Instance Checker - run very early
    name = f"{application.name}-{wx.GetUserId()}"
    checker = wx.SingleInstanceChecker(name)
    if checker.IsAnotherRunning():
        if launch_url:
            try:
                send_ipc_message("open_url", launch_url)
            except Exception:
                pass
        elif "--background" not in sys.argv:
            try:
                send_ipc_message("show")
            except Exception:
                wx.MessageBox(
                    _("البرنامج قيد التشغيل بالفعل."),
                    _("تنبيه"),
                    style=wx.ICON_INFORMATION,
                )
        sys.exit()

    threading.Thread(target=start_async_loop, daemon=True).start()

    lang_id = codes.get(settings_handler.config_get("lang"), wx.LANGUAGE_ARABIC)
    locale = wx.Locale(lang_id)

    start_hidden = "--background" in sys.argv and not launch_url
    home_screen = HomeScreen(start_hidden=start_hidden, launch_url=launch_url)
    app.MainLoop()
