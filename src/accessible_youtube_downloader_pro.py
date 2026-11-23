"""Launch HexPlayer in desktop or browser native messaging mode."""

import sys

# Early setup for MPV and other DLLs
from runtime_dlls import configure_dll_search_path, configure_linux_display_backend

configure_dll_search_path()
# Force XWayland on Wayland sessions before wx/GTK starts, so mpv can embed video
# into a real X11 window (wid embedding is unsupported on native Wayland).
configure_linux_display_backend()

import logging
import threading

import wx

import application
import utils
from app_runtime.async_utils import start_async_loop
from app_runtime.embedded_native_host import (
    is_native_messaging_invocation,
    native_messaging_main,
)
from app_runtime.ipc import send_ipc_message
from app_runtime.logging_setup import (
    enable_console_output,
    is_debug_invocation,
    setup_logging,
)
from app_state import settings_handler
from gui.home_screen import HomeScreen
from language_handler import _, codes

__all__ = [
    "HomeScreen",
    "enable_console_output",
    "get_launch_url",
    "is_debug_invocation",
    "setup_logging",
]

setup_logging()
logger = logging.getLogger(__name__)


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


def get_launch_url(argv):
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        url = utils.extract_launch_youtube_url(arg)
        if url:
            return url
    return ""


def main():
    if is_native_messaging_invocation(sys.argv):
        return native_messaging_main()

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
        return 0

    threading.Thread(target=start_async_loop, daemon=True).start()

    lang_id = codes.get(settings_handler.config_get("lang"), wx.LANGUAGE_ARABIC)
    # Hold the locale and frame alive until the event loop exits.
    _locale = wx.Locale(lang_id)

    start_hidden = "--background" in sys.argv and not launch_url
    _home_screen = HomeScreen(start_hidden=start_hidden, launch_url=launch_url)

    # Warm the heavy YouTube runtimes in the background. They are no longer
    # imported at module load (that cost ~1.3s of the startup time); loading
    # them here, after the window is built and just before MainLoop paints it,
    # keeps the UI instant while they become ready for the first play / search /
    # download and the home-feed prefetch.
    threading.Thread(target=_warm_background_runtimes, daemon=True).start()

    app.MainLoop()


if __name__ == "__main__":
    sys.exit(main())
