"""Region selection for YouTube requests."""

import os


def get_windows_region(default="US"):
    """
    Returns the 2-letter ISO country code for the current Windows region setting.
    Falls back to system locale or default ('US') if unavailable.
    """
    if os.name == "nt":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(10)
            res = ctypes.windll.kernel32.GetUserDefaultGeoName(buf, 10)
            if res > 0 and buf.value:
                code = buf.value.strip().upper()
                if len(code) == 2 and code.isalpha():
                    return code
        except Exception:
            pass

        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\International\Geo"
            )
            name, _ = winreg.QueryValueEx(key, "Name")
            winreg.CloseKey(key)
            if name and isinstance(name, str):
                code = name.strip().upper()
                if len(code) == 2 and code.isalpha():
                    return code
        except Exception:
            pass

        try:
            import ctypes
            import locale

            lcid = ctypes.windll.kernel32.GetUserDefaultLCID()
            win_loc = locale.windows_locale.get(lcid)
            if win_loc and "_" in win_loc:
                code = win_loc.split("_")[-1].strip().upper()
                if len(code) == 2 and code.isalpha():
                    return code
        except Exception:
            pass

    try:
        import locale

        loc = locale.getlocale()[0] or os.environ.get("LANG") or ""
        if "_" in loc:
            code = loc.split("_")[-1].split(".")[0].strip().upper()
            if len(code) == 2 and code.isalpha():
                return code
    except Exception:
        pass

    return default
