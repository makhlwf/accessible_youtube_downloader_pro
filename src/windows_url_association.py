import configparser
import ctypes
import json
import logging
import os
import shlex
import subprocess
import sys

import application
import paths

logger = logging.getLogger(__name__)

APP_REG_NAME = application.name
PROG_ID = f"{application.name}.YouTubeURL"
CAPABILITIES_ROOT = rf"Software\{application.name}"
CAPABILITIES_PATH = rf"{CAPABILITIES_ROOT}\Capabilities"
REGISTERED_APPLICATIONS_PATH = r"Software\RegisteredApplications"
PROG_ID_PATH = rf"Software\Classes\{PROG_ID}"
APPLICATION_PATH = rf"Software\Classes\Applications\{application.name}.exe"
HEXPLAYER_PROTOCOL = "hexplayer"
HEXPLAYER_PROTOCOL_PATH = rf"Software\Classes\{HEXPLAYER_PROTOCOL}"
NATIVE_HOST_NAME = "com.hexplayer.link_helper"
NATIVE_HOST_EXE_NAME = "HexPlayerNativeHost.exe"
EXTENSION_ID = "imldcegpnikhbjndcmffgphmdfokaiml"
NATIVE_HOST_REGISTRY_PATHS = (
    rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}",
    rf"Software\Chromium\NativeMessagingHosts\{NATIVE_HOST_NAME}",
    rf"Software\Microsoft\Edge\NativeMessagingHosts\{NATIVE_HOST_NAME}",
    rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{NATIVE_HOST_NAME}",
)


LINUX_NATIVE_HOST_NAME = "HexPlayerNativeHost"
LINUX_DESKTOP_ID = "hexplayer.desktop"
LINUX_BROWSER_DIRS = (
    "google-chrome",
    "chromium",
    "microsoft-edge",
    "BraveSoftware/Brave-Browser",
)


def get_linux_native_host_manifest_paths():
    return [
        os.path.join(
            paths.get_config_root(),
            browser,
            "NativeMessagingHosts",
            f"{NATIVE_HOST_NAME}.json",
        )
        for browser in LINUX_BROWSER_DIRS
    ]


def _linux_launcher_path():
    return os.path.join(paths.settings_path, "native_messaging", LINUX_NATIVE_HOST_NAME)


def _linux_launcher_content():
    script = os.path.join(paths.get_app_path(), "native_messaging_host.py")
    return f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(script)} "$@"\n'


def _write_linux_launcher():
    launcher = _linux_launcher_path()
    os.makedirs(os.path.dirname(launcher), exist_ok=True)
    with open(launcher, "w", encoding="utf-8", newline="\n") as file:
        file.write(_linux_launcher_content())
    os.chmod(launcher, 0o700)


def _desktop_quote(value):
    if any(character in value for character in ("\n", "\r", "\0")):
        raise ValueError("Invalid desktop command path")
    value = value.replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return '"' + value + '"'


def _linux_desktop_path():
    return os.path.join(paths.get_data_root(), "applications", LINUX_DESKTOP_ID)


def _linux_desktop_content():
    return (
        "[Desktop Entry]\nType=Application\nName=HexPlayer\n"
        f"Exec={get_open_command()}\nTerminal=false\nNoDisplay=true\n"
        f"MimeType=x-scheme-handler/{HEXPLAYER_PROTOCOL};\n"
    )


def _linux_protocol(action):
    try:
        desktop_path = _linux_desktop_path()
        mime_type = f"x-scheme-handler/{HEXPLAYER_PROTOCOL}"
        if action == "register":
            os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
            with open(desktop_path, "w", encoding="utf-8", newline="\n") as file:
                file.write(_linux_desktop_content())
            subprocess.run(
                ["xdg-mime", "default", LINUX_DESKTOP_ID, mime_type],
                check=True,
                capture_output=True,
                timeout=10,
            )
            return True
        if action == "query":
            with open(desktop_path, encoding="utf-8") as file:
                if file.read() != _linux_desktop_content():
                    return False
            result = subprocess.run(
                ["xdg-mime", "query", "default", mime_type],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() == LINUX_DESKTOP_ID
        for root in (paths.get_config_root(), os.path.dirname(desktop_path)):
            mimeapps = os.path.join(root, "mimeapps.list")
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            parser.read(mimeapps, encoding="utf-8")
            changed = False
            for section in parser.sections():
                entries = parser.get(section, mime_type, fallback="").split(";")
                if LINUX_DESKTOP_ID in entries:
                    remaining = [
                        entry
                        for entry in entries
                        if entry and entry != LINUX_DESKTOP_ID
                    ]
                    if remaining:
                        parser.set(section, mime_type, ";".join(remaining) + ";")
                    else:
                        parser.remove_option(section, mime_type)
                    changed = True
            if changed:
                with open(mimeapps, "w", encoding="utf-8") as file:
                    parser.write(file)
        _remove_file(desktop_path)
        return True
    except (OSError, ValueError, subprocess.SubprocessError, configparser.Error) as exc:
        logger.error("Linux protocol %s failed: %s", action, exc)
        return False


def _remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _linux_native_host(action):
    try:
        manifests = get_linux_native_host_manifest_paths()
        if action == "unregister":
            for path in manifests + [
                get_native_host_manifest_path(),
                _linux_launcher_path(),
            ]:
                _remove_file(path)
            return True
        if action == "register":
            if not getattr(sys, "frozen", False):
                _write_linux_launcher()
            manifest_path = write_native_host_manifest()
            with open(manifest_path, encoding="utf-8") as file:
                manifest = json.load(file)
            for path in manifests:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as file:
                    json.dump(manifest, file, ensure_ascii=False, indent=2)
            return True
        executable = get_native_host_executable_path()
        if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
            return False
        if not getattr(sys, "frozen", False):
            with open(executable, encoding="utf-8") as file:
                if file.read() != _linux_launcher_content():
                    return False
        for path in manifests:
            with open(path, encoding="utf-8") as file:
                manifest = json.load(file)
            if manifest != _native_host_manifest():
                return False
        return True
    except (OSError, ValueError) as exc:
        logger.error("Linux native host %s failed: %s", action, exc)
        return False


def _quote_command_part(value):
    return f'"{value}"'


def _get_winreg():
    import winreg

    return winreg


def _set_value(winreg, root, path, name, value):
    key = winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def get_open_command():
    if sys.platform == "linux":
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(
                os.path.join(
                    paths.get_app_path(), "accessible_youtube_downloader_pro.py"
                )
            )
        return " ".join(_desktop_quote(part) for part in command) + " %u"
    if getattr(sys, "frozen", False):
        return f'{_quote_command_part(sys.executable)} "%1"'

    main_module = sys.modules.get("__main__")
    script_path = getattr(main_module, "__file__", None)
    if script_path:
        script_path = os.path.abspath(script_path)
        return f'{_quote_command_part(sys.executable)} {_quote_command_part(script_path)} "%1"'

    return f'{_quote_command_part(sys.executable)} "%1"'


def get_application_icon():
    return f"{sys.executable},0"


def get_native_host_executable_path():
    if sys.platform == "linux":
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), LINUX_NATIVE_HOST_NAME)
        return _linux_launcher_path()
    if getattr(sys, "frozen", False):
        return os.path.join(
            os.path.dirname(sys.executable),
            NATIVE_HOST_EXE_NAME,
        )
    return sys.executable


def get_native_host_manifest_path():
    return os.path.join(
        paths.settings_path,
        "native_messaging",
        f"{NATIVE_HOST_NAME}.json",
    )


def _native_host_manifest():
    return {
        "name": NATIVE_HOST_NAME,
        "description": f"{application.name} browser integration",
        "path": get_native_host_executable_path(),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }


def write_native_host_manifest():
    manifest_path = get_native_host_manifest_path()
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(_native_host_manifest(), file, ensure_ascii=False, indent=2)
    return manifest_path


def _delete_value(winreg, root, path, name):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return
    try:
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
    finally:
        winreg.CloseKey(key)


def _delete_key_tree(winreg, root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return

    try:
        while True:
            try:
                subkey = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_key_tree(winreg, root, rf"{path}\{subkey}")
    finally:
        winreg.CloseKey(key)

    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def _delete_empty_key(winreg, root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return

    try:
        try:
            winreg.EnumKey(key, 0)
            return
        except OSError:
            pass
    finally:
        winreg.CloseKey(key)

    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def _notify_assoc_changed():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x1003, None, None)
    except Exception as e:
        logger.error("Failed to notify Windows about URL association change: %s", e)


def cleanup_legacy_http_url_handler():
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        _delete_value(winreg, root, REGISTERED_APPLICATIONS_PATH, APP_REG_NAME)
        _delete_key_tree(winreg, root, CAPABILITIES_PATH)
        _delete_empty_key(winreg, root, CAPABILITIES_ROOT)
        _delete_key_tree(winreg, root, PROG_ID_PATH)
        _delete_key_tree(winreg, root, APPLICATION_PATH)
        _notify_assoc_changed()
        return True
    except Exception as e:
        logger.error("Failed to clean up legacy URL handler registration: %s", e)
        return False


def register_hexplayer_protocol():
    if sys.platform == "linux":
        return _linux_protocol("register")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER
    command = get_open_command()
    icon = get_application_icon()

    try:
        _set_value(
            winreg,
            root,
            HEXPLAYER_PROTOCOL_PATH,
            "",
            f"URL:{application.name} Browser Integration",
        )
        _set_value(winreg, root, HEXPLAYER_PROTOCOL_PATH, "URL Protocol", "")
        _set_value(winreg, root, rf"{HEXPLAYER_PROTOCOL_PATH}\DefaultIcon", "", icon)
        _set_value(
            winreg,
            root,
            rf"{HEXPLAYER_PROTOCOL_PATH}\shell\open\command",
            "",
            command,
        )
        _notify_assoc_changed()
        return True
    except Exception as e:
        logger.error("Failed to register HexPlayer protocol: %s", e)
        return False


def unregister_hexplayer_protocol():
    if sys.platform == "linux":
        return _linux_protocol("unregister")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        _delete_key_tree(winreg, root, HEXPLAYER_PROTOCOL_PATH)
        _notify_assoc_changed()
        return True
    except Exception as e:
        logger.error("Failed to unregister HexPlayer protocol: %s", e)
        return False


def is_hexplayer_protocol_registered():
    if sys.platform == "linux":
        return _linux_protocol("query")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        key = winreg.OpenKey(root, rf"{HEXPLAYER_PROTOCOL_PATH}\shell\open\command")
        try:
            value, _ = winreg.QueryValueEx(key, "")
        finally:
            winreg.CloseKey(key)
        return value == get_open_command()
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error("Failed to query HexPlayer protocol registration: %s", e)
        return False


def register_native_messaging_host():
    if sys.platform == "linux":
        return _linux_native_host("register")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        manifest_path = write_native_host_manifest()
        for key_path in NATIVE_HOST_REGISTRY_PATHS:
            _set_value(winreg, root, key_path, "", manifest_path)
        return True
    except Exception as e:
        logger.error("Failed to register Native Messaging host: %s", e)
        return False


def unregister_native_messaging_host():
    if sys.platform == "linux":
        return _linux_native_host("unregister")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        for key_path in NATIVE_HOST_REGISTRY_PATHS:
            _delete_key_tree(winreg, root, key_path)
        try:
            os.remove(get_native_host_manifest_path())
        except FileNotFoundError:
            pass
        return True
    except Exception as e:
        logger.error("Failed to unregister Native Messaging host: %s", e)
        return False


def is_native_messaging_host_registered():
    if sys.platform == "linux":
        return _linux_native_host("query")
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER
    manifest_path = get_native_host_manifest_path()

    try:
        for key_path in NATIVE_HOST_REGISTRY_PATHS:
            key = winreg.OpenKey(root, key_path)
            try:
                value, _ = winreg.QueryValueEx(key, "")
            finally:
                winreg.CloseKey(key)
            if value != manifest_path:
                return False
        return os.path.exists(manifest_path)
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error("Failed to query Native Messaging host registration: %s", e)
        return False


def register_browser_integration():
    protocol_ok = register_hexplayer_protocol()
    native_ok = register_native_messaging_host()
    return protocol_ok and native_ok


def unregister_browser_integration():
    protocol_ok = unregister_hexplayer_protocol()
    native_ok = unregister_native_messaging_host()
    return protocol_ok and native_ok


def is_legacy_http_url_handler_registered():
    if sys.platform != "win32":
        return False

    winreg = _get_winreg()
    root = winreg.HKEY_CURRENT_USER

    try:
        key = winreg.OpenKey(root, REGISTERED_APPLICATIONS_PATH)
        try:
            value, _ = winreg.QueryValueEx(key, APP_REG_NAME)
        finally:
            winreg.CloseKey(key)
        return value == CAPABILITIES_PATH
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error("Failed to query legacy URL handler registration: %s", e)
        return False
