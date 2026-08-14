import logging
import os

import paths
import utils

logger = logging.getLogger(__name__)

SUPPORTED_BROWSERS_MAP = {
    "firefox": "Mozilla Firefox",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "brave": "Brave",
    "opera": "Opera",
    "vivaldi": "Vivaldi",
    "chromium": "Chromium",
}


def _get_browser_directories():
    local_app_data = os.getenv("LOCALAPPDATA", "")
    app_data = os.getenv("APPDATA", "")
    return {
        "firefox": [
            os.path.join(app_data, "Mozilla", "Firefox", "Profiles"),
            os.path.join(
                local_app_data,
                "Packages",
                "Mozilla.Firefox_n80bbvh6b1yt2",
                "LocalCache",
                "Roaming",
                "Mozilla",
                "Firefox",
                "Profiles",
            ),
        ],
        "chrome": [
            os.path.join(local_app_data, "Google", "Chrome", "User Data"),
        ],
        "edge": [
            os.path.join(local_app_data, "Microsoft", "Edge", "User Data"),
        ],
        "brave": [
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data"),
        ],
        "opera": [
            os.path.join(app_data, "Opera Software", "Opera Stable"),
            os.path.join(app_data, "Opera Software", "Opera GX Stable"),
        ],
        "vivaldi": [
            os.path.join(local_app_data, "Vivaldi", "User Data"),
        ],
        "chromium": [
            os.path.join(local_app_data, "Chromium", "User Data"),
        ],
    }


def get_installed_browsers():
    """Returns a list of detected installed browsers with id and display name."""
    installed = []
    browser_dirs = _get_browser_directories()

    for browser_id, display_name in SUPPORTED_BROWSERS_MAP.items():
        paths_to_check = browser_dirs.get(browser_id, [])
        is_detected = any(os.path.exists(p) for p in paths_to_check if p)
        if is_detected:
            installed.append({"id": browser_id, "name": display_name, "detected": True})

    # Fallback to all supported if none detected
    if not installed:
        for browser_id, display_name in SUPPORTED_BROWSERS_MAP.items():
            installed.append(
                {"id": browser_id, "name": display_name, "detected": False}
            )

    return installed


def cookie_to_netscape_line(cookie):
    """Converts a standard Cookie object into a Netscape cookie file line."""
    domain = cookie.domain or ""
    flag = "TRUE" if domain.startswith(".") else "FALSE"
    path = cookie.path or "/"
    secure = "TRUE" if cookie.secure else "FALSE"
    expires = str(int(cookie.expires)) if cookie.expires else "0"
    name = cookie.name or ""
    value = cookie.value or ""
    return f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"


def _extract_cookies_from_browser_raw(browser_id):
    """Invokes yt-dlp cookie extraction for the specified browser ID."""
    utils.load_yt_dlp()
    yt_dlp_module = utils.yt_dlp_module
    if not yt_dlp_module:
        raise RuntimeError("yt-dlp is not available to extract cookies.")

    from yt_dlp.cookies import extract_cookies_from_browser

    cookie_jar = extract_cookies_from_browser(browser_id)
    return list(cookie_jar) if cookie_jar else []


def get_default_browser_cookies_path():
    os.makedirs(paths.settings_path, exist_ok=True)
    return os.path.join(paths.settings_path, "browser_cookies.txt")


def extract_and_save_browser_cookies(browser_id, target_path=None):
    """
    Extracts YouTube/Google cookies from the given browser and writes to a Netscape cookie file.
    Returns dict: {'success': bool, 'count': int, 'path': str, 'error': str, 'error_type': str}
    """
    if target_path is None:
        target_path = get_default_browser_cookies_path()

    browser_display = SUPPORTED_BROWSERS_MAP.get(browser_id, browser_id)

    try:
        cookies = _extract_cookies_from_browser_raw(browser_id)
    except Exception as exc:
        err_msg = str(exc)
        logger.error(f"Failed to extract cookies from {browser_id}: {err_msg}")
        lower_err = err_msg.lower()
        if (
            "locked" in lower_err
            or "permission" in lower_err
            or "used by another process" in lower_err
        ):
            error_type = "locked"
        elif "dpapi" in lower_err or "decrypt" in lower_err or "app-bound" in lower_err:
            error_type = "decrypt_failed"
        elif "could not find" in lower_err or "database" in lower_err:
            error_type = "not_found"
        else:
            error_type = "unknown"
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": err_msg,
            "error_type": error_type,
            "browser": browser_display,
        }

    # Filter for youtube/google domains or keep relevant session cookies
    filtered_cookies = []
    for c in cookies:
        domain = (c.domain or "").lower()
        if "youtube" in domain or "google" in domain or "yt" in domain:
            filtered_cookies.append(c)

    # If domain filtering resulted in empty, but cookies exist, preserve all cookies
    if not filtered_cookies and cookies:
        filtered_cookies = cookies

    if not filtered_cookies:
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": "No cookies found in the selected browser.",
            "error_type": "no_cookies",
            "browser": browser_display,
        }

    AUTH_COOKIE_NAMES = {
        "sapisid",
        "__secure-3papisid",
        "login_info",
        "sid",
        "hsid",
        "ssid",
    }
    has_auth = any(
        (c.name or "").lower() in AUTH_COOKIE_NAMES for c in filtered_cookies
    )

    try:
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This file was generated by HexPlayer\n\n")
            for c in filtered_cookies:
                f.write(cookie_to_netscape_line(c))

        logger.info(
            f"Extracted {len(filtered_cookies)} cookies for {browser_display} -> {target_path} (Authenticated: {has_auth})"
        )

        return {
            "success": True,
            "count": len(filtered_cookies),
            "path": target_path,
            "error": None,
            "error_type": None,
            "browser": browser_display,
            "is_authenticated": has_auth,
        }
    except Exception as exc:
        logger.error(f"Failed to write cookies file to {target_path}: {exc}")
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": str(exc),
            "error_type": "write_failed",
            "browser": browser_display,
            "is_authenticated": False,
        }


def save_raw_browser_cookies(cookies, target_path=None):
    """
    Saves a list of cookie dicts (e.g. from browser extension) to a Netscape cookie file.
    Returns: dict {'success': bool, 'count': int, 'path': str, 'error': str | None, 'is_authenticated': bool}
    """
    if target_path is None:
        target_path = get_default_browser_cookies_path()

    if not cookies or not isinstance(cookies, list):
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": "No cookies provided.",
            "error_type": "no_cookies",
            "is_authenticated": False,
        }

    filtered = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain", "")).lower()
        if "youtube" in domain or "google" in domain or "yt" in domain:
            filtered.append(c)

    if not filtered and cookies:
        filtered = [c for c in cookies if isinstance(c, dict)]

    if not filtered:
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": "No valid cookies found.",
            "error_type": "no_cookies",
            "is_authenticated": False,
        }

    AUTH_COOKIE_NAMES = {
        "sapisid",
        "__secure-3papisid",
        "login_info",
        "sid",
        "hsid",
        "ssid",
    }
    has_auth = any(
        str(c.get("name", "")).lower() in AUTH_COOKIE_NAMES for c in filtered
    )

    try:
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n")
            f.write("# This file was generated by HexPlayer\n\n")
            for c in filtered:
                domain = str(c.get("domain", ""))
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = str(c.get("path", "/"))
                secure = "TRUE" if c.get("secure") else "FALSE"
                exp = c.get("expirationDate") or c.get("expires") or 0
                expires = str(int(exp))
                name = str(c.get("name", ""))
                value = str(c.get("value", ""))
                f.write(
                    f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
                )

        logger.info(
            f"Saved {len(filtered)} raw cookies to {target_path} (Authenticated: {has_auth})"
        )

        return {
            "success": True,
            "count": len(filtered),
            "path": target_path,
            "error": None,
            "error_type": None,
            "is_authenticated": has_auth,
        }
    except Exception as exc:
        logger.error(f"Failed to write cookies file to {target_path}: {exc}")
        return {
            "success": False,
            "count": 0,
            "path": target_path,
            "error": str(exc),
            "error_type": "write_failed",
            "is_authenticated": False,
        }
