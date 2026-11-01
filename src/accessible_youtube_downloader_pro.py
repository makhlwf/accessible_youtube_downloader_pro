import ctypes
import json
import os
import socket
import struct
import sys

# Early setup for MPV and other DLLs
from runtime_dlls import configure_dll_search_path, configure_linux_display_backend

configure_dll_search_path()
# Force XWayland on Wayland sessions before wx/GTK starts, so mpv can embed video
# into a real X11 window (wid embedding is unsupported on native Wayland).
configure_linux_display_backend()

import logging
import subprocess
import threading
import webbrowser

import pyperclip
import wx

import application
import browser_extension_manager
import database
import paths
import settings_handler
import utils
import windows_url_association
from async_utils import start_async_loop, stop_async_loop
from deno_service import deno_service
from gui.activity_dialog import LoadingDialog
from gui.custom_controls import CustomLabel
from gui.tray_icon import TaskBarIcon
from language_handler import _, codes, init_translation
from pot_provider_service import pot_service
from speech_client import speak
from theme_handler import apply_theme
from youtube_browser.scraper import Scraper

# NOTE: heavy, feature-specific modules (media_gui/mpv, the YouTube browser,
# per-feature dialogs, yt-dlp) are intentionally NOT imported here. They are
# imported lazily inside the handler that first needs them so the home screen
# can appear without paying their (~1s combined) import cost at launch.


def _warm_background_runtimes():
    """Load the heavy YouTube runtimes off the UI thread, just after launch.

    Both pull in large dependency trees (yt-dlp ~0.9s; py_yt + aiohttp ~0.4s)
    that are not needed to show the home screen, so neither is imported at
    module load any more. Warming them here keeps the window instant while they
    become ready well before the first search / playback / download. Both calls
    are idempotent, so the lazy consumers that may also trigger them are safe.
    """
    try:
        utils.load_yt_dlp()
    except Exception:
        logger.debug("Background yt-dlp warmup failed", exc_info=True)
    try:
        # Windows-only shim that stops py_yt's botGuard subprocess from flashing
        # a console window; importing py_yt here is what costs the ~0.4s.
        utils.configure_py_yt_subprocess()
    except Exception:
        logger.debug("Background py_yt subprocess shim failed", exc_info=True)


def is_debug_invocation(argv=None):
    if argv is None:
        argv = sys.argv
    return any(arg in ("-d", "--debug") for arg in argv[1:])


def get_launch_url(argv):
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        url = utils.extract_launch_youtube_url(arg)
        if url:
            return url
    return ""


def enable_console_output():
    if sys.platform != "win32":
        return True

    try:
        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            kernel32.AllocConsole()

        try:
            sys.stdout = open(  # noqa: SIM115
                "CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1
            )
        except Exception:
            pass
        try:
            sys.stderr = open(  # noqa: SIM115
                "CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1
            )
        except Exception:
            pass
        try:
            sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")  # noqa: SIM115
        except Exception:
            pass
        return True
    except Exception:
        return False


def setup_logging(argv=None):
    os.makedirs(paths.settings_path, exist_ok=True)
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    is_debug_cli = is_debug_invocation(argv)
    is_debug_config = False
    try:
        settings_handler.config_initialization()
        is_debug_config = bool(settings_handler.config_get("debug"))
    except Exception:
        pass

    is_debug = is_debug_cli or is_debug_config

    if is_debug_cli:
        enable_console_output()

    root_logger.setLevel(logging.DEBUG if is_debug else logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_h = logging.StreamHandler(sys.stderr)
    console_h.setFormatter(formatter)
    root_logger.addHandler(console_h)

    try:
        file_h = logging.FileHandler(paths.log_path, encoding="utf-8", mode="a")
        file_h.setFormatter(formatter)
        root_logger.addHandler(file_h)
    except Exception:
        pass

    try:
        from logging_config import apply_logging_settings

        apply_logging_settings()
    except Exception:
        pass

    if is_debug:
        if is_debug_cli:
            root_logger.debug("Debug logging initialized (terminal output enabled)")
        else:
            root_logger.debug("Debug logging initialized")


setup_logging()
logger = logging.getLogger(__name__)
IPC_HOST = "127.0.0.1"
IPC_PORT = 57280


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
        msg_type = message.get("type")
        if msg_type == "open":
            url = message.get("url", "")
            opened = launch_or_forward_external_url(url)
            write_native_message({"ok": opened})
            return 0 if opened else 1
        elif msg_type == "save_cookies":
            cookies = message.get("cookies", [])
            import cookies_manager

            result = cookies_manager.save_raw_browser_cookies(cookies)
            if result.get("success"):
                settings_handler.config_set("cookiespath", result["path"])
                try:
                    send_ipc_message("cookies_updated", result["path"])
                except Exception:
                    pass
                write_native_message(
                    {
                        "ok": True,
                        "count": result.get("count", 0),
                        "path": result.get("path", ""),
                    }
                )
                return 0
            write_native_message(
                {"ok": False, "error": result.get("error", "Failed to save cookies")}
            )
            return 1

        write_native_message({"ok": False, "error": "Unsupported message type"})
        return 1
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
        self.scraper = Scraper(owner=self)
        self.home_feed_continuation = None
        self.last_clip_content = ""
        self.pending_launch_url = launch_url
        self.tray_icon = TaskBarIcon(self)

        # Search tab data
        self.search_data = None
        self.search_results = None
        self.search_scraper = Scraper(owner=self)

        # Shorts tab data
        self.shorts_data = []
        self.shorts_loading = False

        # Subscriptions tab data
        self.sub_feed_videos = []
        self.sub_feed_continuation = None
        self.sub_feed_results = None
        self.sub_feed_scraper = Scraper(owner=self)
        self.sub_feed_loading = False

        # Watch history tab data
        self.history_data = []
        self.history_continuation = None
        self.history_results = None
        self.history_scraper = Scraper(owner=self)
        self.history_loading = False

        # Favorites tab data
        self.favorites = database.Favorite()
        self.fav_rows = []

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
        self._startup_logic()
        try:
            import discord_presence

            discord_presence.init_presence()
            discord_presence.update_idle()
        except Exception:
            logger.debug(
                "Failed to initialize discord presence on startup", exc_info=True
            )
        if hasattr(self, "notebook") and self.notebook:
            self.notebook.SetFocus()
        if self.pending_launch_url:
            self.handle_external_url(self.pending_launch_url)

    def _init_ui(self):
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)

        self.main_panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self.notebook = wx.Notebook(self.main_panel, -1, name="home_tabs")

        # Tab 1: Home page (home feed only)
        self.home_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.panel = self.home_tab  # Backwards compatibility alias
        self.instruction = CustomLabel(self.home_tab, -1, "")
        self.instruction.Hide()

        self.home_feed_list = wx.ListBox(self.home_tab, -1, name="home_feed")
        self.home_feed_list.Hide()
        self.load_more_home_button = wx.Button(
            self.home_tab, -1, _("تحميل المزيد من الفيديوهات المقترحة")
        )
        self.load_more_home_button.Hide()

        home_sizer = wx.BoxSizer(wx.VERTICAL)
        home_sizer.Add(self.home_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        home_sizer.Add(self.load_more_home_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.home_tab.SetSizer(home_sizer)

        # Tab 2: Search tab
        self.search_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.search_query_lbl = wx.StaticText(
            self.search_tab, -1, _("ابحث في youtube: ")
        )
        self.search_query_ctrl = wx.TextCtrl(
            self.search_tab, -1, style=wx.TE_PROCESS_ENTER, name=_("ابحث في youtube")
        )
        self.search_filter_box = wx.Choice(
            self.search_tab,
            -1,
            choices=[
                _("بلا فلتر"),
                _("بث مباشر"),
                _("تاريخ الرفع"),
                _("عدد المشاهدات"),
                _("قائمة تشغيل"),
                _("قنوات"),
            ],
            name=_("فلتر"),
        )
        self.search_filter_box.SetSelection(0)
        self.search_submit_btn = wx.Button(
            self.search_tab, -1, _("ابحث"), name="search_submit"
        )
        self.search_suggestions_list = wx.ListBox(
            self.search_tab,
            -1,
            size=(-1, 120),
            style=wx.LB_SINGLE,
            name=_("اقتراحات البحث"),
        )
        self.search_suggestions_list.Hide()
        self.search_results_list = wx.ListBox(
            self.search_tab, -1, name=_("نتائج البحث")
        )
        self.search_play_btn = wx.Button(
            self.search_tab, -1, _("تشغيل (Enter)"), name="play_search"
        )
        self.search_download_btn = wx.Button(
            self.search_tab, -1, _("تنزيل"), name="download_search"
        )
        self.search_load_more_btn = wx.Button(
            self.search_tab,
            -1,
            _("تحميل المزيد من النتائج"),
            name="load_more_search",
        )
        self.search_load_more_btn.Hide()

        for btn in (
            self.search_submit_btn,
            self.search_play_btn,
            self.search_download_btn,
            self.search_load_more_btn,
        ):
            btn.SetName(btn.GetLabel())

        search_sizer = wx.BoxSizer(wx.VERTICAL)
        search_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_input_sizer.Add(
            self.search_query_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
        )
        search_input_sizer.Add(self.search_query_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        search_input_sizer.Add(
            self.search_filter_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
        )
        search_input_sizer.Add(self.search_submit_btn, 0, wx.ALL, 5)

        search_sizer.Add(search_input_sizer, 0, wx.EXPAND | wx.ALL, 5)
        search_sizer.Add(self.search_suggestions_list, 0, wx.EXPAND | wx.ALL, 5)
        search_sizer.Add(self.search_results_list, 1, wx.EXPAND | wx.ALL, 5)

        search_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_btn_sizer.Add(self.search_play_btn, 0, wx.ALL, 5)
        search_btn_sizer.Add(self.search_download_btn, 0, wx.ALL, 5)
        search_btn_sizer.Add(self.search_load_more_btn, 0, wx.ALL, 5)
        search_sizer.Add(search_btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.search_tab.SetSizer(search_sizer)

        # Tab 3: Operations tab (combines play from link and download from link)
        self.ops_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.ops_download_path = settings_handler.config_get("path")

        ops_sizer = wx.BoxSizer(wx.VERTICAL)

        ops_url_box = wx.StaticBox(self.ops_tab, -1, _("الرابط"))
        ops_url_sizer = wx.StaticBoxSizer(ops_url_box, wx.VERTICAL)
        ops_url_row = wx.BoxSizer(wx.HORIZONTAL)
        ops_url_lbl = wx.StaticText(
            self.ops_tab, -1, _("رابط الفيديو أو قائمة التشغيل: ")
        )
        self.ops_url_ctrl = wx.TextCtrl(
            self.ops_tab, -1, style=wx.TE_PROCESS_ENTER, name=_("رابط المقطع")
        )
        self.ops_paste_btn = wx.Button(
            self.ops_tab, -1, _("لصق من الحافظة"), name="paste_url"
        )
        ops_url_row.Add(ops_url_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        ops_url_row.Add(self.ops_url_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        ops_url_row.Add(self.ops_paste_btn, 0, wx.ALL, 5)
        ops_url_sizer.Add(ops_url_row, 0, wx.EXPAND | wx.ALL, 5)
        ops_sizer.Add(ops_url_sizer, 0, wx.EXPAND | wx.ALL, 10)

        ops_play_box = wx.StaticBox(self.ops_tab, -1, _("التشغيل المباشر من الرابط"))
        ops_play_sizer = wx.StaticBoxSizer(ops_play_box, wx.VERTICAL)
        self.ops_play_mode_radio = wx.RadioBox(
            self.ops_tab,
            -1,
            _("وضع التشغيل:"),
            choices=[
                _("حسب الإعدادات الافتراضية"),
                _("مقطع صوتي"),
                _("مقطع فيديو"),
            ],
        )
        self.ops_play_btn = wx.Button(
            self.ops_tab, -1, _("تشغيل (Enter)"), name="play_from_link"
        )
        ops_play_sizer.Add(self.ops_play_mode_radio, 0, wx.EXPAND | wx.ALL, 5)
        ops_play_sizer.Add(self.ops_play_btn, 0, wx.ALL, 5)
        ops_sizer.Add(ops_play_sizer, 0, wx.EXPAND | wx.ALL, 10)

        ops_dl_box = wx.StaticBox(self.ops_tab, -1, _("تنزيل المقطع من الرابط"))
        ops_dl_sizer = wx.StaticBoxSizer(ops_dl_box, wx.VERTICAL)
        self.ops_download_format = wx.RadioBox(
            self.ops_tab,
            -1,
            _("نوع التنزيل"),
            choices=[_("صوت"), _("فيديو")],
        )
        ops_format_row = wx.BoxSizer(wx.HORIZONTAL)
        ops_format_lbl = wx.StaticText(
            self.ops_tab, -1, _("صيغة المقطع:"), name="convert"
        )
        self.ops_converting_format = wx.Choice(
            self.ops_tab,
            -1,
            choices=["m4a", "mp3", "wav", "flac"],
            name="convert",
        )
        default_audio = int(settings_handler.config_get("defaultaudio"))
        if not (0 <= default_audio < self.ops_converting_format.GetCount()):
            default_audio = 0
        self.ops_converting_format.SetSelection(default_audio)
        ops_format_row.Add(ops_format_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        ops_format_row.Add(self.ops_converting_format, 1, wx.EXPAND | wx.ALL, 5)

        self.ops_change_path_btn = wx.Button(
            self.ops_tab,
            -1,
            f"{_('مسار مجلد التنزيل: ')} {self.ops_download_path}",
        )
        self.ops_download_btn = wx.Button(
            self.ops_tab, -1, _("بدء التنزيل"), name="start_download"
        )

        ops_dl_sizer.Add(self.ops_download_format, 0, wx.EXPAND | wx.ALL, 5)
        ops_dl_sizer.Add(ops_format_row, 0, wx.EXPAND | wx.ALL, 5)
        ops_dl_sizer.Add(self.ops_change_path_btn, 0, wx.EXPAND | wx.ALL, 5)
        ops_dl_sizer.Add(self.ops_download_btn, 0, wx.ALL, 5)
        ops_sizer.Add(ops_dl_sizer, 0, wx.EXPAND | wx.ALL, 10)

        for btn in (
            self.ops_paste_btn,
            self.ops_play_btn,
            self.ops_change_path_btn,
            self.ops_download_btn,
        ):
            btn.SetName(btn.GetLabel())

        self.ops_tab.SetSizer(ops_sizer)

        # Tab 4: Shorts tab
        self.shorts_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.shorts_list = wx.ListBox(
            self.shorts_tab, -1, name=_("فيديوهات Shorts المقترحة")
        )
        self.play_shorts_btn = wx.Button(
            self.shorts_tab, -1, _("تشغيل (Enter)"), name="play_shorts"
        )
        self.shortsBtn = self.play_shorts_btn  # Compatibility alias
        self.refresh_shorts_btn = wx.Button(
            self.shorts_tab, -1, _("تحديث فيديوهات Shorts"), name="refresh_shorts"
        )

        for btn in (
            self.play_shorts_btn,
            self.refresh_shorts_btn,
        ):
            btn.SetName(btn.GetLabel())

        shorts_sizer = wx.BoxSizer(wx.VERTICAL)
        shorts_sizer.Add(self.shorts_list, 1, wx.EXPAND | wx.ALL, 5)
        shorts_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        shorts_btn_sizer.Add(self.play_shorts_btn, 0, wx.ALL, 5)
        shorts_btn_sizer.Add(self.refresh_shorts_btn, 0, wx.ALL, 5)
        shorts_sizer.Add(shorts_btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.shorts_tab.SetSizer(shorts_sizer)

        # Tab 5: Subscriptions tab
        self.subs_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.sub_feed_list = wx.ListBox(
            self.subs_tab, -1, name=_("Subscription videos, newest first")
        )
        self.sub_feed_status = wx.StaticText(self.subs_tab, label="")
        self.open_sub_channels_btn = wx.Button(
            self.subs_tab,
            -1,
            _("القنوات المشترك بها\tctrl+shift+u"),
            name="subscribed_channels",
        )
        self.subscriptionsBtn = self.open_sub_channels_btn  # Compatibility alias
        self.play_sub_btn = wx.Button(
            self.subs_tab, -1, _("تشغيل (Enter)"), name="play_sub"
        )
        self.load_more_subs_btn = wx.Button(
            self.subs_tab,
            -1,
            _("تحميل المزيد من فيديوهات الاشتراكات"),
            name="load_more_subs",
        )
        self.load_more_subs_btn.Hide()
        self.refresh_subs_btn = wx.Button(
            self.subs_tab,
            -1,
            _("Refresh subscriptions feed"),
            name="Subscriptions feed",
        )
        self.subscriptionsFeedBtn = self.refresh_subs_btn  # Compatibility alias

        for btn in (
            self.open_sub_channels_btn,
            self.play_sub_btn,
            self.load_more_subs_btn,
            self.refresh_subs_btn,
        ):
            btn.SetName(btn.GetLabel())
        self.subscriptionsFeedBtn.SetName(_("Subscriptions feed"))

        subs_sizer = wx.BoxSizer(wx.VERTICAL)
        subs_sizer.Add(self.sub_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        subs_sizer.Add(self.sub_feed_status, 0, wx.EXPAND | wx.ALL, 5)
        subs_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        subs_btn_sizer.Add(self.open_sub_channels_btn, 0, wx.ALL, 5)
        subs_btn_sizer.Add(self.play_sub_btn, 0, wx.ALL, 5)
        subs_btn_sizer.Add(self.load_more_subs_btn, 0, wx.ALL, 5)
        subs_btn_sizer.Add(self.refresh_subs_btn, 0, wx.ALL, 5)
        subs_sizer.Add(subs_btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.subs_tab.SetSizer(subs_sizer)

        # Tab 6: Watch History tab
        self.history_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.history_list = wx.ListBox(self.history_tab, -1, name=_("سجل المشاهدة"))
        self.history_status = wx.StaticText(self.history_tab, label="")
        self.history_play_btn = wx.Button(
            self.history_tab, -1, _("تشغيل (Enter)"), name="play_history"
        )
        self.history_download_btn = wx.Button(
            self.history_tab, -1, _("تنزيل"), name="download_history"
        )
        self.history_fav_btn = wx.Button(
            self.history_tab, -1, _("تفضيل الفيديو"), name="fav_history"
        )
        self.load_more_history_btn = wx.Button(
            self.history_tab,
            -1,
            _("تحميل المزيد من السجل"),
            name="load_more_history",
        )
        self.load_more_history_btn.Hide()
        self.refresh_history_btn = wx.Button(
            self.history_tab,
            -1,
            _("تحديث السجل"),
            name="refresh_history",
        )

        for btn in (
            self.history_play_btn,
            self.history_download_btn,
            self.history_fav_btn,
            self.load_more_history_btn,
            self.refresh_history_btn,
        ):
            btn.SetName(btn.GetLabel())

        history_sizer = wx.BoxSizer(wx.VERTICAL)
        history_sizer.Add(self.history_list, 1, wx.EXPAND | wx.ALL, 5)
        history_sizer.Add(self.history_status, 0, wx.EXPAND | wx.ALL, 5)
        history_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        history_btn_sizer.Add(self.history_play_btn, 0, wx.ALL, 5)
        history_btn_sizer.Add(self.history_download_btn, 0, wx.ALL, 5)
        history_btn_sizer.Add(self.history_fav_btn, 0, wx.ALL, 5)
        history_btn_sizer.Add(self.load_more_history_btn, 0, wx.ALL, 5)
        history_btn_sizer.Add(self.refresh_history_btn, 0, wx.ALL, 5)
        history_sizer.Add(history_btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.history_tab.SetSizer(history_sizer)

        # Tab 7: Favorite videos tab
        self.fav_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)
        self.fav_list = wx.ListBox(self.fav_tab, -1, name=_("الفيديوهات المفضلة"))
        self.fav_status = wx.StaticText(self.fav_tab, label="")
        self.fav_play_btn = wx.Button(
            self.fav_tab, -1, _("تشغيل (Enter)"), name="play_favorite"
        )
        self.fav_download_btn = wx.Button(
            self.fav_tab, -1, _("تنزيل"), name="download_favorite"
        )
        self.fav_delete_btn = wx.Button(
            self.fav_tab, -1, _("إلغاء التفضيل"), name="delete_favorite"
        )
        self.fav_refresh_btn = wx.Button(
            self.fav_tab,
            -1,
            _("تحديث المفضلة"),
            name="refresh_favorite",
        )

        for btn in (
            self.fav_play_btn,
            self.fav_download_btn,
            self.fav_delete_btn,
            self.fav_refresh_btn,
        ):
            btn.SetName(btn.GetLabel())

        fav_sizer = wx.BoxSizer(wx.VERTICAL)
        fav_sizer.Add(self.fav_list, 1, wx.EXPAND | wx.ALL, 5)
        fav_sizer.Add(self.fav_status, 0, wx.EXPAND | wx.ALL, 5)
        fav_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        fav_btn_sizer.Add(self.fav_play_btn, 0, wx.ALL, 5)
        fav_btn_sizer.Add(self.fav_download_btn, 0, wx.ALL, 5)
        fav_btn_sizer.Add(self.fav_delete_btn, 0, wx.ALL, 5)
        fav_btn_sizer.Add(self.fav_refresh_btn, 0, wx.ALL, 5)
        fav_sizer.Add(fav_btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.fav_tab.SetSizer(fav_sizer)

        # Tab 8: YouTube Music tab
        self.music_tab = wx.Panel(self.notebook, style=wx.TAB_TRAVERSAL)

        # Add pages to notebook
        self.notebook.AddPage(self.home_tab, _("الصفحة الرئيسية"))
        self.notebook.AddPage(self.search_tab, _("البحث"))
        self.notebook.AddPage(self.ops_tab, _("العمليات"))
        self.notebook.AddPage(self.shorts_tab, _("فيديوهات Shorts"))
        self.notebook.AddPage(self.subs_tab, _("الاشتراكات"))
        self.notebook.AddPage(self.history_tab, _("سجل المشاهدة"))
        self.notebook.AddPage(self.fav_tab, _("الفيديوهات المفضلة"))
        self.notebook.AddPage(self.music_tab, _("يوتيوب ميوزك"))

        # Hidden action buttons preserved for backwards compatibility with tests and callers
        self.searchBtn = wx.Button(
            self.main_panel, -1, _("البحث في يوتيوب\tctrl+f"), name="tab"
        )
        self.searchBtn.Hide()
        self.downloadBtn = wx.Button(
            self.main_panel, -1, _("التنزيل من خلال رابط\tctrl+d"), name="tab"
        )
        self.downloadBtn.Hide()
        self.playBtn = wx.Button(
            self.main_panel,
            -1,
            _("تشغيل فيديو يوتيوب من خلال الرابط\tctrl+y"),
            name="tab",
        )
        self.playBtn.Hide()
        self.historyBtn = self.history_play_btn
        self.favBtn = self.fav_play_btn
        self.musicBtn = wx.Button(
            self.main_panel, -1, _("يوتيوب ميوزك\tctrl+m"), name="tab"
        )
        self.musicBtn.Hide()

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND)
        self.main_panel.SetSizer(main_sizer)

        # Root frame sizer so a sibling YouTube Music panel can be flipped in
        # place (shown/hidden) without opening a new window. Built lazily.
        self._root_sizer = wx.BoxSizer(wx.VERTICAL)
        self._root_sizer.Add(self.main_panel, 1, wx.EXPAND)
        self.SetSizer(self._root_sizer)
        self.music_panel = None
        self._in_music_mode = False

    def _setup_menus(self):
        menuBar = wx.MenuBar()

        # Main Menu
        mainMenu = wx.Menu()
        self.searchItem = mainMenu.Append(-1, _("البحث في يوتيوب\tctrl+f"))
        self.downloadItem = mainMenu.Append(-1, _("التنزيل من خلال رابط\tctrl+d"))
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

        # Notebook event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

        # Buttons (compatibility)
        self.searchBtn.Bind(wx.EVT_BUTTON, self.onSearch)
        self.downloadBtn.Bind(wx.EVT_BUTTON, self.onDownload)
        self.playBtn.Bind(wx.EVT_BUTTON, self.onPlay)
        self.favBtn.Bind(wx.EVT_BUTTON, self.onFavorite)
        self.historyBtn.Bind(wx.EVT_BUTTON, self.onHistory)
        self.musicBtn.Bind(wx.EVT_BUTTON, self.onMusic)
        self.Bind(wx.EVT_SHOW, self._on_frame_show)

        # Tab 1: Home feed
        self.load_more_home_button.Bind(
            wx.EVT_BUTTON, lambda event: self.load_home_feed(True)
        )
        self.home_feed_list.Bind(wx.EVT_LISTBOX, self.on_home_feed_list_box)
        self.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_home_feed_play(
                event, audio_mode=self.get_effective_audio_mode(invert=False)
            ),
            self.home_feed_list,
        )
        self.home_feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_home_feed_hook)

        # Tab 2: Search tab
        self.search_suggest_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_search_suggest_timer, self.search_suggest_timer)
        self.search_query_ctrl.Bind(wx.EVT_TEXT, self.on_search_query_text)
        self.search_query_ctrl.Bind(wx.EVT_TEXT_ENTER, lambda event: self.do_search())
        self.search_submit_btn.Bind(wx.EVT_BUTTON, lambda event: self.do_search())
        self.search_suggestions_list.Bind(
            wx.EVT_LISTBOX_DCLICK, self.on_search_suggestion_selected
        )
        self.search_suggestions_list.Bind(
            wx.EVT_KEY_DOWN, self.on_search_suggestion_key
        )
        self.search_results_list.Bind(wx.EVT_LISTBOX, self.on_search_result_list_box)
        self.search_results_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_play_search_result(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.search_results_list.Bind(wx.EVT_CHAR_HOOK, self.on_search_results_hook)
        self.search_play_btn.Bind(
            wx.EVT_BUTTON,
            lambda event: self.on_play_search_result(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.search_download_btn.Bind(wx.EVT_BUTTON, self.on_download_search_result)
        self.search_load_more_btn.Bind(
            wx.EVT_BUTTON, lambda event: self.load_more_search_results()
        )

        # Tab 3: Operations tab
        self.ops_paste_btn.Bind(wx.EVT_BUTTON, self.on_ops_paste)
        self.ops_play_btn.Bind(wx.EVT_BUTTON, lambda event: self.on_ops_play())
        self.ops_url_ctrl.Bind(wx.EVT_CHAR_HOOK, self.on_ops_url_hook)
        self.ops_download_format.Bind(
            wx.EVT_RADIOBOX, self.on_ops_download_format_changed
        )
        self.ops_change_path_btn.Bind(wx.EVT_BUTTON, self.on_ops_change_path)
        self.ops_download_btn.Bind(wx.EVT_BUTTON, self.on_ops_download)

        # Tab 4: Shorts
        self.shorts_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_play_short(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.shorts_list.Bind(wx.EVT_CHAR_HOOK, self.on_shorts_hook)
        self.play_shorts_btn.Bind(
            wx.EVT_BUTTON,
            lambda event: self.on_play_short(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.refresh_shorts_btn.Bind(
            wx.EVT_BUTTON, lambda event: self.load_shorts_feed(refresh=True)
        )

        # Tab 5: Subscriptions
        self.sub_feed_list.Bind(wx.EVT_LISTBOX, self.on_sub_feed_list_box)
        self.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_play_sub_video(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
            self.sub_feed_list,
        )
        self.sub_feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_sub_feed_hook)
        self.open_sub_channels_btn.Bind(wx.EVT_BUTTON, self.on_open_subscriptions)
        self.play_sub_btn.Bind(
            wx.EVT_BUTTON,
            lambda event: self.on_play_sub_video(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.load_more_subs_btn.Bind(
            wx.EVT_BUTTON, lambda event: self.load_subs_feed(load_more=True)
        )
        self.refresh_subs_btn.Bind(wx.EVT_BUTTON, self.on_open_subscriptions_feed)

        # Tab 6: Watch History
        self.history_list.Bind(wx.EVT_LISTBOX, self.on_history_list_box)
        self.history_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_play_history(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.history_list.Bind(wx.EVT_CHAR_HOOK, self.on_history_list_hook)
        self.history_play_btn.Bind(
            wx.EVT_BUTTON,
            lambda event: self.on_play_history(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.history_download_btn.Bind(wx.EVT_BUTTON, self.on_download_history)
        self.history_fav_btn.Bind(wx.EVT_BUTTON, self.on_toggle_history_favorite)
        self.load_more_history_btn.Bind(
            wx.EVT_BUTTON, lambda event: self.load_history(load_more=True)
        )
        self.refresh_history_btn.Bind(
            wx.EVT_BUTTON, lambda event: self.load_history(load_more=False)
        )

        # Tab 7: Favorite videos
        self.fav_list.Bind(
            wx.EVT_LISTBOX_DCLICK,
            lambda event: self.on_play_favorite(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.fav_list.Bind(wx.EVT_CHAR_HOOK, self.on_fav_list_hook)
        self.fav_play_btn.Bind(
            wx.EVT_BUTTON,
            lambda event: self.on_play_favorite(
                audio_mode=self.get_effective_audio_mode(invert=False)
            ),
        )
        self.fav_download_btn.Bind(wx.EVT_BUTTON, self.on_download_favorite)
        self.fav_delete_btn.Bind(wx.EVT_BUTTON, self.on_delete_favorite)
        self.fav_refresh_btn.Bind(wx.EVT_BUTTON, lambda event: self.load_favorites())

        # Frame events
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, self.onClose)

    def get_effective_audio_mode(self, invert=False):
        try:
            is_audio = int(settings_handler.config_get("defaultaudio")) == 0
        except ValueError, TypeError:
            is_audio = True
        return not is_audio if invert else is_audio

    def on_tab_changed(self, event):
        sel = self.notebook.GetSelection()
        if sel == 0:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("الصفحة الرئيسية"))
            if self.home_feed_list.IsShown():
                self.home_feed_list.SetFocus()
        elif sel == 1:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("البحث"))
            if hasattr(self, "search_query_ctrl"):
                self.search_query_ctrl.SetFocus()
        elif sel == 2:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("العمليات"))
            if hasattr(self, "ops_url_ctrl"):
                if not self.ops_url_ctrl.GetValue().strip():
                    self.detect_ops_url_from_clipboard()
                self.ops_url_ctrl.SetFocus()
        elif sel == 3:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("فيديوهات Shorts"))
            if not self.shorts_data and utils.has_cookies_file():
                self.load_shorts_feed()
            if hasattr(self, "shorts_list"):
                self.shorts_list.SetFocus()
        elif sel == 4:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("الاشتراكات"))
            if not self.sub_feed_videos and utils.has_cookies_file():
                self.load_subs_feed()
            if hasattr(self, "sub_feed_list"):
                self.sub_feed_list.SetFocus()
        elif sel == 5:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("سجل المشاهدة"))
            if not self.history_data and utils.has_cookies_file():
                self.load_history()
            if hasattr(self, "history_list"):
                self.history_list.SetFocus()
        elif sel == 6:
            if self._in_music_mode:
                self._in_music_mode = False
                if self.music_panel is not None:
                    self.music_panel.Hide()
            self.panel.Show()
            speak(_("الفيديوهات المفضلة"))
            self.load_favorites()
            if hasattr(self, "fav_list"):
                self.fav_list.SetFocus()
        elif sel == 7:
            speak(_("يوتيوب ميوزك"))
            self.open_music()
        event.Skip()

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
            self.load_shorts_feed()
            self.load_subs_feed()
            self.load_history()
        self.load_favorites()

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
        if not load_more:
            self.home_feed_list.Set([_("جاري تحميل الاقتراحات... يرجى الانتظار")])
            self.home_feed_list.Show()
            self.Layout()

        continuation = self.home_feed_continuation if load_more else None

        def _load():
            try:
                data = utils.get_home_feed(continuation, parent=self)
                wx.CallAfter(self._update_home_feed, data, load_more)
            except Exception as e:
                logger.error(f"Failed to load home feed: {e}")

        # Run feed loading in a thread to keep UI responsive
        threading.Thread(target=_load, daemon=True).start()

    def _update_home_feed(self, data, load_more=False):
        from youtube_browser.search_handler import SimpleResult

        if isinstance(data, dict) and data.get("error"):
            err_msg = data["error"]
            wx.MessageBox(
                err_msg,
                _("تنبيه"),
                style=wx.OK | wx.ICON_WARNING,
                parent=self,
            )
            speak(err_msg)

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

    def on_home_feed_play(self, event, audio_mode=None):
        from media_player.media_gui import MediaGui, play_mix

        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        selection = self.home_feed_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        video_data = self.home_feed_data[selection]
        if video_data.get("type") == "mix":
            logger.info(
                "home feed: selected item is a mix (playlistId=%s seed=%s) -> play_mix",
                video_data.get("playlistId"),
                video_data.get("id"),
            )
            play_mix(
                self,
                video_data.get("playlistId"),
                video_data.get("id"),
                audio_mode=audio_mode,
            )
            self.Hide()
            return
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
            if self.home_feed_data[n].get("type") != "mix":
                self.scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.home_feed_results.count)):
                    if self.home_feed_data[i].get("type") == "mix":
                        continue
                    self.scraper.add_item(i, priority=10)

    def on_home_feed_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_home_feed_play(
                None,
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown()),
            )
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

    def onPlay(self, event=None):
        if hasattr(self, "notebook") and hasattr(self, "ops_tab"):
            self.notebook.SetSelection(2)
            self.detect_ops_url_from_clipboard()
            if hasattr(self, "ops_url_ctrl"):
                self.ops_url_ctrl.SetFocus()
                self.ops_url_ctrl.SelectAll()
        else:
            from gui.link_dlg import LinkDlg
            from media_player.media_gui import MediaGui, play_mix

            linkDlg = LinkDlg(self)
            data = getattr(linkDlg, "data", None)
            if not data or not data.get("link"):
                return
            url = data["link"]
            audio_mode = data.get("audio", False)
            if not utils.check_yt_dlp(self):
                return
            mix_id = utils.extract_mix_id(url)
            if mix_id:
                play_mix(
                    self,
                    mix_id,
                    utils.extract_video_id(url),
                    audio_mode=audio_mode,
                )
                self.Hide()
                return
            stream = LoadingDialog(
                self,
                _("جاري التشغيل"),
                utils.get_playable_stream,
                url,
                audio_mode,
            ).res
            if stream is None:
                utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
                return
            MediaGui(self, stream.title, stream, url, audio_mode=audio_mode)
            self.Hide()

    def onDownload(self, event=None):
        if hasattr(self, "notebook") and hasattr(self, "ops_tab"):
            self.notebook.SetSelection(2)
            self.detect_ops_url_from_clipboard()
            if hasattr(self, "ops_url_ctrl"):
                self.ops_url_ctrl.SetFocus()
                self.ops_url_ctrl.SelectAll()
        else:
            from gui.download_dialog import DownloadDialog

            DownloadDialog(self).Show()

    def detect_ops_url_from_clipboard(self):
        try:
            clip = pyperclip.paste()
            detected = utils.extract_supported_youtube_url(clip)
            if detected and hasattr(self, "ops_url_ctrl"):
                self.ops_url_ctrl.SetValue(detected)
        except Exception:
            pass

    def on_ops_paste(self, event=None):
        try:
            clip = pyperclip.paste()
            detected = utils.extract_supported_youtube_url(clip)
            if detected:
                self.ops_url_ctrl.SetValue(detected)
                speak(_("تم لصق الرابط من الحافظة."))
            elif clip and clip.strip():
                self.ops_url_ctrl.SetValue(clip.strip())
            if hasattr(self, "ops_url_ctrl"):
                self.ops_url_ctrl.SetFocus()
        except Exception:
            pass

    def on_ops_play(self, audio_mode=None):
        url = self.ops_url_ctrl.GetValue().strip()
        if not url or not utils.is_supported_youtube_url(url):
            utils.show_error(
                _("يرجى إدخال رابط صحيح."),
                parent=self,
            )
            self.ops_url_ctrl.SetFocus()
            return

        if audio_mode is None:
            mode_sel = (
                self.ops_play_mode_radio.GetSelection()
                if hasattr(self, "ops_play_mode_radio")
                else 0
            )
            if mode_sel == 1:
                audio_mode = True
            elif mode_sel == 2:
                audio_mode = False
            else:
                audio_mode = self.get_effective_audio_mode(invert=False)

        if not utils.check_yt_dlp(self):
            return

        from media_player.media_gui import MediaGui, play_mix

        mix_id = utils.extract_mix_id(url)
        if mix_id:
            play_mix(self, mix_id, utils.extract_video_id(url), audio_mode=audio_mode)
            self.Hide()
            return

        stream = LoadingDialog(
            self,
            _("جاري التشغيل"),
            utils.get_playable_stream,
            url,
            audio_mode,
        ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return
        MediaGui(self, stream.title, stream, url, audio_mode=audio_mode)
        self.Hide()

    def on_ops_url_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_ops_play(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        else:
            event.Skip()

    def on_ops_download_format_changed(self, event):
        if self.ops_download_format.GetSelection() == 0:
            self.ops_converting_format.SetItems(["m4a", "mp3", "wav", "flac"])
            default_audio = int(settings_handler.config_get("defaultaudio"))
            if not (0 <= default_audio < self.ops_converting_format.GetCount()):
                default_audio = 0
            self.ops_converting_format.SetSelection(default_audio)
        else:
            self.ops_converting_format.SetItems(["mp4", "mkv"])
            self.ops_converting_format.SetSelection(0)

    def on_ops_change_path(self, event=None):
        path = wx.DirSelector(
            _("اختر مجلد التنزيل"),
            self.ops_download_path or paths.get_default_download_dir(),
            parent=self,
        )
        if path:
            self.ops_download_path = path
            self.ops_change_path_btn.SetLabel(f"{_('مسار مجلد التنزيل: ')} {path}")

    def on_ops_download(self, event=None):
        url = self.ops_url_ctrl.GetValue().strip()
        if not url or not utils.is_supported_youtube_url(url):
            utils.show_error(
                _("يرجى إدخال رابط صحيح."),
                parent=self,
            )
            self.ops_url_ctrl.SetFocus()
            return
        cases = ("list", "channel", "playlist", "/user/", "/c/", "/@", "RD", "mix")
        folder = any(case in url for case in cases)
        if not utils.check_yt_dlp(self):
            return
        format_str = self.ops_converting_format.GetStringSelection()
        from download_handler.downloader import start_media_download

        start_media_download(
            url,
            format_str,
            self,
            path=self.ops_download_path,
            folder=folder,
        )

    def onSearch(self, event=None):
        if hasattr(self, "notebook") and hasattr(self, "search_tab"):
            self.notebook.SetSelection(1)
            if hasattr(self, "search_query_ctrl"):
                self.search_query_ctrl.SetFocus()
                self.search_query_ctrl.SelectAll()
        else:
            from youtube_browser.browser import YoutubeBrowser

            YoutubeBrowser(self)

    def on_search_query_text(self, event):
        if hasattr(self, "search_suggest_timer"):
            self.search_suggest_timer.Stop()
            self.search_suggest_timer.Start(350, oneShot=True)
        event.Skip()

    def on_search_suggest_timer(self, event):
        query = self.search_query_ctrl.GetValue().strip()
        if not query:
            self.search_suggestions_list.Hide()
            self.search_tab.Layout()
            return

        def _fetch():
            from youtube_browser.search_handler import fetch_search_suggestions

            try:
                suggestions = fetch_search_suggestions(query)
            except Exception:
                suggestions = []
            wx.CallAfter(self._update_search_suggestions, suggestions)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_search_suggestions(self, suggestions):
        if not suggestions:
            self.search_suggestions_list.Hide()
        else:
            self.search_suggestions_list.Set(suggestions)
            self.search_suggestions_list.Show()
        self.search_tab.Layout()

    def on_search_suggestion_selected(self, event=None):
        sel = self.search_suggestions_list.GetSelection()
        if sel != wx.NOT_FOUND:
            text = self.search_suggestions_list.GetString(sel)
            self.search_query_ctrl.SetValue(text)
            self.search_suggestions_list.Hide()
            self.search_tab.Layout()
            self.do_search()

    def on_search_suggestion_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_search_suggestion_selected()
        elif event.GetKeyCode() == wx.WXK_ESCAPE:
            self.search_suggestions_list.Hide()
            self.search_tab.Layout()
            self.search_query_ctrl.SetFocus()
        else:
            event.Skip()

    def do_search(self, query=None, filter_val=None):
        if query is None:
            query = self.search_query_ctrl.GetValue().strip()
        if not query:
            return
        if filter_val is None:
            filter_val = self.search_filter_box.GetSelection()

        try:
            from database import SearchHistory

            SearchHistory.add(query)
        except Exception:
            pass

        self.search_suggestions_list.Hide()
        self.search_tab.Layout()
        self.search_results_list.Set([_("جاري البحث... يرجى الانتظار")])
        self.search_load_more_btn.Hide()
        speak(_("جاري البحث..."), interrupt=True)

        from youtube_browser.search_handler import Search

        def _fetch():
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    search_obj = loop.run_until_complete(
                        Search(query, filter_val).init_async()
                    )
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
                wx.CallAfter(self._update_search_results, search_obj, None)
            except Exception as e:
                logger.error(f"Search failed: {e}")
                wx.CallAfter(self._update_search_results, None, e)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_search_results(self, search_obj, error):
        if error is not None:
            err = _("تعذر إجراء عملية البحث بسبب وجود خلل ما في الاتصال بالشبكة.")
            speak(err)
            self.search_results_list.Set([err])
            return

        if not search_obj:
            err = _("لم يتم العثور على نتائج.")
            speak(err)
            self.search_results_list.Set([err])
            return

        self.search_data = search_obj
        self.search_results = search_obj
        self.search_scraper.set_results(search_obj)
        titles = search_obj.get_titles() if hasattr(search_obj, "get_titles") else []
        if not titles:
            msg = _("لم يتم العثور على نتائج.")
            self.search_results_list.Set([msg])
            speak(msg)
            self.search_load_more_btn.Hide()
        else:
            self.search_results_list.Set(titles)
            self.search_results_list.SetSelection(0)
            self.search_results_list.SetFocus()
            has_more = getattr(search_obj, "has_more", False) or getattr(
                search_obj, "_has_more", False
            )
            self.search_load_more_btn.Show(bool(has_more))
            count_msg = _("تم العثور على {count} نتيجة").format(count=len(titles))
            speak(count_msg)

            for i in range(min(5, getattr(search_obj, "count", len(titles)))):
                self.search_scraper.add_item(i, priority=10)
        self.search_tab.Layout()

    def on_search_result_list_box(self, event):
        sel = self.search_results_list.GetSelection()
        if 0 <= sel < getattr(self.search_data, "count", 0):
            self.search_scraper.add_item(sel, priority=0)

    def on_play_search_result(self, audio_mode=None):
        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        sel = self.search_results_list.GetSelection()
        if sel == wx.NOT_FOUND or not self.search_data:
            return
        if sel >= getattr(self.search_data, "count", 0):
            return

        item = self.search_data.get_result(sel)
        if not item:
            return

        item_type = item.get("type", "video")
        if item_type == "channel":
            from gui.channel_dialog import ChannelDialog

            ChannelDialog(self, item["url"])
            return
        if item_type == "playlist":
            from gui.playlist_dialog import PlaylistDialog

            PlaylistDialog(self, item["url"])
            return

        url = item.get("url")
        if not url:
            return

        stream = self.search_data.get_stream(sel, audio_mode=audio_mode)
        if stream is None:
            if not utils.check_yt_dlp(self):
                return
            stream = LoadingDialog(
                self,
                _("جاري التشغيل"),
                utils.get_playable_stream,
                url,
                audio_mode,
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return

        from media_player.media_gui import MediaGui

        MediaGui(
            self,
            title=item.get("title", ""),
            stream=stream,
            url=url,
            audio_mode=audio_mode,
            results=self.search_data,
        )
        self.Hide()

    def on_search_results_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_play_search_result(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        else:
            event.Skip()

    def on_download_search_result(self, event=None):
        sel = self.search_results_list.GetSelection()
        if sel == wx.NOT_FOUND or not self.search_data:
            return
        item = self.search_data.get_result(sel)
        if item and item.get("url"):
            from gui.download_dialog import DownloadDialog

            DownloadDialog(self, url=item["url"]).Show()

    def load_more_search_results(self):
        if not self.search_data:
            return

        def _fetch():
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(
                        self.search_data.load_more_async()
                        if hasattr(self.search_data, "load_more_async")
                        else self.search_data.get_next_page()
                    )
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
                wx.CallAfter(self._update_load_more_search, res)
            except Exception as e:
                logger.error(f"Failed to load more search results: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_load_more_search(self, result):
        if not self.search_data:
            return
        titles = self.search_data.get_titles()
        old_count = self.search_results_list.GetCount()
        self.search_results_list.Set(titles)
        new_count = len(titles)
        has_more = getattr(self.search_data, "has_more", False) or getattr(
            self.search_data, "_has_more", False
        )
        self.search_load_more_btn.Show(bool(has_more))
        speak(
            _("Loaded {count} more search results.").format(count=new_count - old_count)
        )
        for i in range(old_count, min(old_count + 5, new_count)):
            self.search_scraper.add_item(i, priority=10)
        self.search_tab.Layout()

    def onHistory(self, event=None):
        if not utils.has_cookies_file():
            utils.show_error(
                _("يجب تحديد ملف الكوكيز من الإعدادات لعرض سجل المشاهدة."),
                parent=self,
            )
            return

        if hasattr(self, "notebook") and hasattr(self, "history_tab"):
            self.notebook.SetSelection(5)
            if not self.history_data:
                self.load_history()
            if hasattr(self, "history_list"):
                self.history_list.SetFocus()
        else:
            from gui.history import HistoryDialog

            HistoryDialog(self)

    def load_history(self, load_more=False):
        if not utils.has_cookies_file():
            if hasattr(self, "history_list"):
                self.history_list.Set(
                    [_("يجب تحديد ملف الكوكيز من الإعدادات لعرض سجل المشاهدة.")]
                )
            return
        if self.history_loading:
            return
        self.history_loading = True
        if not load_more:
            if hasattr(self, "history_list"):
                self.history_list.Set([_("جاري تحميل السجل... يرجى الانتظار")])
            speak(_("جاري تحميل السجل..."))
        else:
            speak(_("جاري تحميل المزيد من السجل"))

        def _load():
            try:
                data = utils.get_watch_history(
                    self.history_continuation if load_more else None, parent=self
                )
            except Exception as e:
                logger.error(f"Failed to load watch history: {e}")
                data = {"error": str(e)}
            finally:
                self.history_loading = False
            wx.CallAfter(self._update_history, data, load_more)

        threading.Thread(target=_load, daemon=True).start()

    def _update_history(self, data, load_more=False):
        from youtube_browser.search_handler import SimpleResult

        if isinstance(data, dict) and data.get("error"):
            err_msg = data["error"]
            utils.show_error(err_msg, parent=self)
            speak(err_msg)

        new_videos = data.get("videos", []) if isinstance(data, dict) else []
        self.history_continuation = (
            data.get("continuation") if isinstance(data, dict) else None
        )

        old_count = len(self.history_data)
        if load_more:
            self.history_data.extend(new_videos)
        else:
            self.history_data = new_videos
            if hasattr(self, "history_list"):
                self.history_list.Clear()

        self.history_results = SimpleResult(self.history_data)
        if hasattr(self, "history_scraper"):
            self.history_results.scraper = self.history_scraper
            self.history_scraper.set_results(self.history_results)

        titles = [f"{item['title']} - {item['author']}" for item in self.history_data]
        if hasattr(self, "history_list"):
            self.history_list.Set(titles)

        if hasattr(self, "load_more_history_btn"):
            if self.history_continuation:
                self.load_more_history_btn.Show()
            else:
                self.load_more_history_btn.Hide()

        if not self.history_data and hasattr(self, "history_list"):
            self.history_list.Set([_("لا يوجد سجل مشاهدة متاح")])

        if hasattr(self, "history_tab"):
            self.history_tab.Layout()
        if load_more:
            speak(_("تم تحميل المزيد من السجل"))
            if hasattr(self, "history_scraper") and self.history_results:
                for i in range(old_count, self.history_results.count):
                    self.history_scraper.add_item(i, priority=10)
        else:
            speak(_("تم تحميل السجل"))
            if hasattr(self, "history_scraper") and self.history_results:
                for i in range(min(10, self.history_results.count)):
                    self.history_scraper.add_item(i, priority=10)
        self.update_history_fav_button()

    def update_history_fav_button(self):
        if not hasattr(self, "history_fav_btn") or not hasattr(self, "history_list"):
            return
        sel = self.history_list.GetSelection()
        if (
            sel == wx.NOT_FOUND
            or not self.history_data
            or sel >= len(self.history_data)
        ):
            self.history_fav_btn.SetLabel(_("تفضيل الفيديو"))
            return
        url = self.history_data[sel].get("url", "")
        if self.favorites.get_favorite(url):
            self.history_fav_btn.SetLabel(_("إلغاء التفضيل"))
        else:
            self.history_fav_btn.SetLabel(_("تفضيل الفيديو"))

    def on_history_list_box(self, event):
        self.update_history_fav_button()
        if not hasattr(self, "history_list"):
            return
        n = self.history_list.GetSelection()
        if (
            n != wx.NOT_FOUND
            and hasattr(self, "history_scraper")
            and self.history_results
        ):
            self.history_scraper.add_item(n, priority=0)
            if n > 0 and n % 10 == 0:
                for i in range(n, min(n + 10, self.history_results.count)):
                    self.history_scraper.add_item(i, priority=10)

    def on_toggle_history_favorite(self, event=None):
        if not hasattr(self, "history_list"):
            return
        sel = self.history_list.GetSelection()
        if (
            sel == wx.NOT_FOUND
            or not self.history_data
            or sel >= len(self.history_data)
        ):
            return
        video_data = self.history_data[sel]
        url = video_data.get("url", "")
        if self.favorites.get_favorite(url):
            self.favorites.remove_favorite(url)
            self.update_history_fav_button()
            speak(_("تم حذف الفيديو من قائمة المفضلة"))
        else:
            title = video_data.get("title", "")
            author = video_data.get("author", "")
            data = {
                "title": title,
                "display_title": f"{title}. {author}",
                "url": url,
                "live": 1 if video_data.get("is_live") else 0,
                "channel_url": "",
                "channel_name": author,
            }
            self.favorites.add_favorite(data)
            self.update_history_fav_button()
            speak(_("تمت إضافة الفيديو إلى قائمة المفضلة"))

    def on_play_history(self, audio_mode=None):
        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        if not hasattr(self, "history_list"):
            return
        sel = self.history_list.GetSelection()
        if (
            sel == wx.NOT_FOUND
            or not self.history_data
            or sel >= len(self.history_data)
        ):
            return
        video_data = self.history_data[sel]
        url = video_data["url"]
        title = video_data["title"]

        stream = (
            self.history_results.get_stream(sel, audio_mode=audio_mode)
            if self.history_results
            else None
        )
        if stream is None:
            if not utils.check_yt_dlp(self):
                return
            stream = LoadingDialog(
                self,
                _("جاري التشغيل"),
                utils.get_playable_stream,
                url,
                audio_mode,
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return

        from media_player.media_gui import MediaGui

        MediaGui(
            self,
            title,
            stream,
            url,
            audio_mode=audio_mode,
            results=self.history_results,
        )
        self.Hide()

    def on_download_history(self, event=None):
        if not hasattr(self, "history_list"):
            return
        sel = self.history_list.GetSelection()
        if (
            sel == wx.NOT_FOUND
            or not self.history_data
            or sel >= len(self.history_data)
        ):
            return
        url = self.history_data[sel].get("url")
        if url:
            from gui.download_dialog import DownloadDialog

            DownloadDialog(self, url=url).Show()

    def on_history_list_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_play_history(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        elif event.KeyCode == ord("D") and event.ControlDown():
            self.on_download_history()
        elif event.KeyCode in (ord("C"), ord("L")) and event.ControlDown():
            sel = self.history_list.GetSelection()
            if (
                sel != wx.NOT_FOUND
                and self.history_data
                and sel < len(self.history_data)
            ):
                utils.copy_to_clipboard(self.history_data[sel]["url"])
                speak(_("تم نسخ رابط المقطع بنجاح"))
        else:
            event.Skip()

    def _ensure_music_panel(self):
        if self.music_panel is None:
            from youtube_music.music_panel import YouTubeMusicPanel

            parent_tab = getattr(self, "music_tab", self)
            self.music_panel = YouTubeMusicPanel(parent_tab, self)
            if hasattr(self, "music_tab") and self.music_tab:
                music_sizer = wx.BoxSizer(wx.VERTICAL)
                music_sizer.Add(self.music_panel, 1, wx.EXPAND)
                self.music_tab.SetSizer(music_sizer)
                self.music_tab.Layout()
            else:
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
            if hasattr(self, "panel"):
                self.panel.Hide()
            if hasattr(self, "notebook") and self.notebook.GetSelection() != 7:
                self.notebook.SetSelection(7)
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
        if hasattr(self, "panel"):
            self.panel.Show()
        if hasattr(self, "notebook") and self.notebook.GetSelection() != 0:
            self.notebook.SetSelection(0)
        self._root_sizer.Layout()
        try:
            if hasattr(self, "musicBtn"):
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
        if hasattr(self, "notebook") and self.notebook.GetSelection() != 7:
            self.notebook.SetSelection(7)
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
            if not self.home_feed_list.IsShown() or not self.home_feed_data:
                self.load_home_feed()
            if not self.shorts_data:
                self.load_shorts_feed()
            if not self.sub_feed_videos:
                self.load_subs_feed()
        else:
            self.home_feed_list.Hide()
            self.load_more_home_button.Hide()
            self.panel.Layout()
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
        if hasattr(self, "subs_tab"):
            self.subs_tab.Layout()
        if hasattr(self, "shorts_tab"):
            self.shorts_tab.Layout()
        if hasattr(self, "panel"):
            self.panel.Layout()

    def load_shorts_feed(self, refresh=False):
        if not utils.has_cookies_file():
            self.shorts_list.Set(
                [_("يجب تحديد ملف الكوكيز من الإعدادات لاستخدام ميزة Shorts.")]
            )
            return
        if self.shorts_loading:
            return
        self.shorts_loading = True
        if not self.shorts_data or refresh:
            self.shorts_list.Set(
                [_("جاري تحميل فيديوهات Shorts المقترحة... يرجى الانتظار")]
            )
        speak(_("جاري تحميل فيديوهات Shorts المقترحة..."))

        def _fetch():
            try:
                data = utils.get_shorts_feed()
                wx.CallAfter(self._update_shorts_feed, data)
            except Exception as e:
                logger.error(f"Failed to fetch shorts feed: {e}")
                wx.CallAfter(self._update_shorts_feed, [])

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_shorts_feed(self, data):
        self.shorts_loading = False
        self.shorts_data = data or []
        if not self.shorts_data:
            self.shorts_list.Set([_("لا تتوفر فيديوهات Shorts حالياً.")])
            speak(_("لا تتوفر فيديوهات Shorts حالياً."))
            return
        titles = []
        for item in self.shorts_data:
            t = item.get("title", "")
            a = item.get("author", "")
            titles.append(f"{t} - {a}" if a else t)
        self.shorts_list.Set(titles)
        if titles:
            self.shorts_list.SetSelection(0)
        speak(_("تم تحميل {} فيديو Shorts").format(len(self.shorts_data)))
        self.shorts_tab.Layout()

    def on_play_short(self, audio_mode=None):
        if not utils.has_cookies_file():
            utils.show_error(
                _("يجب تحديد ملف الكوكيز من الإعدادات لاستخدام ميزة Shorts."),
                parent=self,
            )
            return
        if not self.shorts_data:
            return
        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        sel = self.shorts_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self.shorts_data):
            sel = 0
        short_item = self.shorts_data[sel]
        url = short_item.get("url")
        title = short_item.get("title", "")
        if not url:
            return

        stream = LoadingDialog(
            self,
            _("جاري جلب رابط التشغيل..."),
            utils.get_playable_stream,
            url,
            audio_mode=audio_mode,
        ).res

        if not stream:
            utils.show_error(_("تعذر استخراج رابط تشغيل الفيديو."), parent=self)
            return

        from media_player.media_gui import MediaGui

        MediaGui(
            self,
            title=title,
            stream=stream,
            url=url,
            can_download=True,
            results=self.shorts_data,
            audio_mode=audio_mode,
            shorts_mode=True,
        )
        self.Hide()

    def on_shorts_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_play_short(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        else:
            event.Skip()

    def load_subs_feed(self, load_more=False):
        if not utils.has_cookies_file():
            self.sub_feed_list.Set(
                [
                    _(
                        "Import YouTube cookies in Settings to view your subscriptions feed."
                    )
                ]
            )
            return
        if self.sub_feed_loading:
            return
        self.sub_feed_loading = True
        continuation = self.sub_feed_continuation if load_more else None
        if not self.sub_feed_videos or not load_more:
            self.sub_feed_list.Set([_("Loading subscriptions feed...")])
        msg = (
            _("Loading more subscription videos...")
            if load_more
            else _("Loading subscriptions feed...")
        )
        speak(msg)

        def _fetch():
            try:
                data = utils.get_subscriptions_feed(continuation)
                wx.CallAfter(self._update_subs_feed, data, load_more)
            except Exception as e:
                logger.error(f"Failed to fetch subscriptions feed: {e}")
                wx.CallAfter(self._update_subs_feed, {"error": str(e)}, load_more)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_subs_feed(self, data, load_more=False):
        from youtube_browser.search_handler import SimpleResult

        self.sub_feed_loading = False
        if not isinstance(data, dict) or data.get("error"):
            err = (
                data.get("error")
                if isinstance(data, dict)
                else _("Could not load subscriptions feed. Please try again.")
            )
            speak(err)
            return

        new_videos = data.get("videos", [])
        self.sub_feed_continuation = data.get("continuation")
        old_count = len(self.sub_feed_videos) if load_more else 0
        if load_more:
            seen = {v["id"] for v in self.sub_feed_videos}
            for v in new_videos:
                if isinstance(v, dict) and v.get("id") and v["id"] not in seen:
                    self.sub_feed_videos.append(v)
                    seen.add(v["id"])
        else:
            self.sub_feed_videos = list(new_videos)

        self.sub_feed_results = SimpleResult(self.sub_feed_videos)
        self.sub_feed_results.scraper = self.sub_feed_scraper
        self.sub_feed_scraper.set_results(self.sub_feed_results)

        if not self.sub_feed_videos:
            self.sub_feed_list.Set(
                [_("No videos from subscribed channels are available.")]
            )
            self.load_more_subs_btn.Hide()
        else:
            labels = [
                _("{title}, channel: {channel}, published: {published}").format(
                    title=v.get("title") or _("Untitled video"),
                    channel=v.get("author") or _("Unknown channel"),
                    published=v.get("published_time")
                    or _("Publication time unavailable"),
                )
                for v in self.sub_feed_videos
            ]
            self.sub_feed_list.Set(labels)
            if not load_more and labels:
                self.sub_feed_list.SetSelection(0)
            self.load_more_subs_btn.Show(self.sub_feed_continuation is not None)
            count_msg = (
                _("Loaded {count} more subscription videos.").format(
                    count=len(self.sub_feed_videos) - old_count
                )
                if load_more
                else _("Loaded {count} subscription videos, newest first.").format(
                    count=len(self.sub_feed_videos)
                )
            )
            speak(count_msg)

            for index in range(
                old_count, min(old_count + 5, len(self.sub_feed_videos))
            ):
                self.sub_feed_scraper.add_item(index, priority=10)

        self.subs_tab.Layout()

    def on_sub_feed_list_box(self, event):
        sel = self.sub_feed_list.GetSelection()
        if 0 <= sel < len(self.sub_feed_videos):
            self.sub_feed_scraper.add_item(sel, priority=0)

    def on_play_sub_video(self, audio_mode=None):
        if not self.sub_feed_videos:
            return
        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        sel = self.sub_feed_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self.sub_feed_videos):
            sel = 0
        video = self.sub_feed_videos[sel]
        url = video.get("url")
        if not url:
            return

        stream = self.sub_feed_results.get_stream(sel, audio_mode=audio_mode)
        if stream is None:
            if not utils.check_yt_dlp(self):
                return
            stream = LoadingDialog(
                self,
                _("جاري التشغيل"),
                utils.get_playable_stream,
                url,
                audio_mode,
            ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return

        from media_player.media_gui import MediaGui

        MediaGui(
            self,
            title=video.get("title", ""),
            stream=stream,
            url=url,
            audio_mode=audio_mode,
            results=self.sub_feed_results,
        )
        self.Hide()

    def on_sub_feed_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_play_sub_video(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        else:
            event.Skip()

    def on_open_subscriptions_feed(self, event=None):
        from unittest.mock import MagicMock

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
        if (
            hasattr(self, "notebook")
            and hasattr(self.notebook, "SetSelection")
            and not isinstance(self, MagicMock)
        ):
            self.notebook.SetSelection(4)
            self.load_subs_feed()
            if hasattr(self, "sub_feed_list"):
                self.sub_feed_list.SetFocus()
        else:
            SubscriptionsFeed(
                self, return_focus=getattr(self, "subscriptionsFeedBtn", None)
            )

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
        if not utils.has_cookies_file():
            utils.show_error(
                _("يجب تحديد ملف الكوكيز من الإعدادات لاستخدام ميزة Shorts."),
                parent=self,
            )
            return

        if hasattr(self, "notebook"):
            self.notebook.SetSelection(3)
        if not self.shorts_data:
            self.load_shorts_feed()
        if hasattr(self, "shorts_list"):
            self.shorts_list.SetFocus()

    def onFavorite(self, event=None):
        if hasattr(self, "notebook") and hasattr(self, "fav_tab"):
            self.notebook.SetSelection(6)
            self.load_favorites()
            if hasattr(self, "fav_list"):
                self.fav_list.SetFocus()
        else:
            from gui.favorites import Favorites

            Favorites(self)

    def load_favorites(self):
        self.fav_rows = self.favorites.get_all()
        titles = [row["display_title"] for row in self.fav_rows]
        if hasattr(self, "fav_list"):
            self.fav_list.Set(titles)
            if not self.fav_rows:
                self.fav_list.Set([_("لا توجد مقاطع مفضلة")])
            else:
                if self.fav_list.GetSelection() == wx.NOT_FOUND:
                    self.fav_list.SetSelection(0)
        if hasattr(self, "fav_tab"):
            self.fav_tab.Layout()

    def on_play_favorite(self, audio_mode=None):
        if audio_mode is None:
            audio_mode = self.get_effective_audio_mode(invert=False)
        if not hasattr(self, "fav_list"):
            return
        sel = self.fav_list.GetSelection()
        if sel == wx.NOT_FOUND or not self.fav_rows or sel >= len(self.fav_rows):
            return
        row = self.fav_rows[sel]
        url = row["url"]
        title = row["title"]

        if not utils.check_yt_dlp(self):
            return
        stream = LoadingDialog(
            self,
            _("جاري التشغيل"),
            utils.get_playable_stream,
            url,
            audio_mode,
        ).res
        if stream is None:
            utils.show_error(_("لا يمكن تشغيل الرابط"), parent=self)
            return

        from media_player.media_gui import MediaGui

        MediaGui(
            self,
            title,
            stream,
            url,
            audio_mode=audio_mode,
        )
        self.Hide()

    def on_download_favorite(self, event=None):
        if not hasattr(self, "fav_list"):
            return
        sel = self.fav_list.GetSelection()
        if sel == wx.NOT_FOUND or not self.fav_rows or sel >= len(self.fav_rows):
            return
        url = self.fav_rows[sel].get("url")
        if url:
            from gui.download_dialog import DownloadDialog

            DownloadDialog(self, url=url).Show()

    def on_delete_favorite(self, event=None):
        if not hasattr(self, "fav_list"):
            return
        sel = self.fav_list.GetSelection()
        if sel == wx.NOT_FOUND or not self.fav_rows or sel >= len(self.fav_rows):
            return
        url = self.fav_rows[sel]["url"]
        self.favorites.remove_favorite(url)
        self.fav_rows.pop(sel)
        titles = [row["display_title"] for row in self.fav_rows]
        self.fav_list.Set(titles)
        if not self.fav_rows:
            self.fav_list.Set([_("لا توجد مقاطع مفضلة")])
        else:
            new_sel = min(sel, len(self.fav_rows) - 1)
            self.fav_list.SetSelection(new_sel)
        speak(_("تم حذف الفيديو من قائمة المفضلة"))

    def on_fav_list_hook(self, event):
        if event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_play_favorite(
                audio_mode=self.get_effective_audio_mode(invert=event.ControlDown())
            )
        elif event.KeyCode == wx.WXK_DELETE:
            self.on_delete_favorite()
        elif event.KeyCode == ord("D") and event.ControlDown():
            self.on_download_favorite()
        elif event.KeyCode in (ord("C"), ord("L")) and event.ControlDown():
            sel = self.fav_list.GetSelection()
            if sel != wx.NOT_FOUND and self.fav_rows and sel < len(self.fav_rows):
                utils.copy_to_clipboard(self.fav_rows[sel]["url"])
                speak(_("تم نسخ رابط المقطع بنجاح"))
        else:
            event.Skip()

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
        if not self.checked:
            if not settings_handler.config_get("welcome_completed"):
                wx.CallAfter(self.show_welcome_screen)
            else:
                # Deferred off the synchronous Show() path so dependency probing
                # (which can lazily import yt-dlp) never blocks the first paint.
                wx.CallAfter(self.startup_dependency_checks)
            self.checked = True
        if hasattr(self, "notebook") and self.notebook:
            self.notebook.SetFocus()
        elif hasattr(self, "instruction") and self.instruction:
            self.instruction.SetFocus()
        event.Skip()

    def show_welcome_screen(self):
        from gui.welcome_dialog import WelcomeDialog

        dlg = WelcomeDialog(self)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
            if hasattr(self, "notebook") and self.notebook:
                self.notebook.SetFocus()
            elif hasattr(self, "instruction") and self.instruction:
                self.instruction.SetFocus()

    def onWelcomeTour(self, event=None):
        self.show_welcome_screen()

    def startup_dependency_checks(self):
        if utils.check_yt_dlp(self) and utils.check_deno(self):
            utils.ensure_js_dependencies()
        utils.check_pot_provider(self)

    def onGuide(self, event):
        from doc_handler import documentation_get
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
        if hasattr(self, "notebook") and self.notebook:
            self.notebook.SetFocus()
        elif hasattr(self, "instruction") and self.instruction:
            self.instruction.SetFocus()

    def onAbout(self, event):
        about = f"""{_("اسم البرنامج")}: {application.name}.
{_("الإصدار")}: {application.version}.
{_("طُوِرَ بواسطة")}: {application.author}.
{_("الوصف: ")}{_(application.description)}."""
        wx.MessageBox(about, _("حول"), parent=self)

    def onExit(self, event=None):
        self.clip_timer.Stop()
        self.tray_icon.Destroy()
        database.disconnect()
        settings_handler.save_settings()
        deno_service.stop()
        pot_service.stop()
        if hasattr(self, "search_scraper") and self.search_scraper:
            try:
                self.search_scraper.close()
            except Exception:
                pass
        if hasattr(self, "sub_feed_scraper") and self.sub_feed_scraper:
            try:
                self.sub_feed_scraper.close()
            except Exception:
                pass
        if hasattr(self, "scraper") and self.scraper:
            try:
                self.scraper.close()
            except Exception:
                pass
        stop_async_loop()
        try:
            import discord_presence

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
            elif action == "cookies_updated":
                wx.CallAfter(self.update_shorts_button_visibility)

        def listen():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind((IPC_HOST, IPC_PORT))
                s.listen(1)
                while True:
                    conn, _addr = s.accept()
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

    # Warm the heavy YouTube runtimes in the background. They are no longer
    # imported at module load (that cost ~1.3s of the startup time); loading
    # them here, after the window is built and just before MainLoop paints it,
    # keeps the UI instant while they become ready for the first play / search /
    # download and the home-feed prefetch.
    threading.Thread(target=_warm_background_runtimes, daemon=True).start()

    app.MainLoop()
