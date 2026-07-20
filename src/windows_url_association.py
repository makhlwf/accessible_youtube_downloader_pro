import ctypes
import json
import logging
import os
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


def write_native_host_manifest():
    manifest_path = get_native_host_manifest_path()
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    manifest = {
        "name": NATIVE_HOST_NAME,
        "description": f"{application.name} browser integration",
        "path": get_native_host_executable_path(),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
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
