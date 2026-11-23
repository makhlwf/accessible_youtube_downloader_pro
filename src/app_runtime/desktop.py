"""Desktop integration, clipboard access, and dialog helpers."""

import importlib
import logging
import os
import subprocess
import sys

import wx

import application
import paths
from app_state.settings_handler import config_get
from language_handler import _

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class _WindowlessSubprocess:
    def __init__(self, module):
        self._module = module

    def __getattr__(self, name):
        return getattr(self._module, name)

    def check_output(self, *args, **kwargs):
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            )
        return self._module.check_output(*args, **kwargs)


def configure_py_yt_subprocess():
    if sys.platform != "win32":
        return
    module = importlib.import_module("py_yt.botGuard.bot_guard")
    if not isinstance(module.subprocess, _WindowlessSubprocess):
        module.subprocess = _WindowlessSubprocess(module.subprocess)


def show_error(message, exception=None, parent=None):
    if not wx.IsMainThread():
        wx.CallAfter(show_error, message, exception, parent)
        return
    if config_get("debug") and exception:
        message = f"{message}\n\nDebug Info:\n{exception!s}"
    wx.MessageBox(
        message,
        _("خطأ"),
        style=wx.ICON_ERROR,
        parent=parent or wx.GetApp().GetTopWindow(),
    )


def _desktop_exec_argument(value):
    value = str(value).replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    value = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return f'"{value}"'


def _set_linux_startup(enable):
    config_home = os.environ.get("XDG_CONFIG_HOME", "")
    if not os.path.isabs(config_home):
        config_home = os.path.expanduser("~/.config")
    autostart_dir = os.path.join(config_home, "autostart")
    desktop_path = os.path.join(autostart_dir, "hexplayer.desktop")
    if not enable:
        try:
            os.remove(desktop_path)
        except FileNotFoundError:
            pass
        return
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(
            os.path.join(paths.get_app_path(), "accessible_youtube_downloader_pro.py")
        )
    command.append("--background")
    exec_line = " ".join(_desktop_exec_argument(arg) for arg in command)
    os.makedirs(autostart_dir, exist_ok=True)
    with open(desktop_path, "w", encoding="utf-8", newline="\n") as desktop:
        desktop.write(
            "[Desktop Entry]\nType=Application\nName=HexPlayer\n"
            f"Exec={exec_line}\nTerminal=false\n"
        )


def set_startup(enable: bool):
    if sys.platform == "linux":
        try:
            _set_linux_startup(enable)
        except OSError:
            logger.exception("Failed to update XDG autostart entry")
        return
    if sys.platform != "win32":
        return
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = application.name
    if getattr(sys, "frozen", False):
        exe_path = f'"{sys.executable}" --background'
    else:
        # For development environments
        script_path = os.path.abspath(sys.modules["__main__"].__file__)
        exe_path = f'"{sys.executable}" "{script_path}" --background'

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        )
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to update startup registry: {e}")


def ensure_focus(window):
    if not window:
        return
    window.Raise()
    window.SetFocus()
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.user32.SetForegroundWindow(window.GetHandle())
        except Exception as e:
            logger.error(f"Failed to SetForegroundWindow: {e}")


def copy_to_clipboard(text):
    import pyperclip

    pyperclip.copy(text)
    try:
        app = wx.GetApp()
        if app:
            top_win = app.GetTopWindow()
            if top_win and hasattr(top_win, "last_clip_content"):
                top_win.last_clip_content = text
    except Exception:
        pass
