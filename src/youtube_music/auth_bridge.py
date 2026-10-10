"""Build ytmusicapi browser-auth headers from the app's existing cookie file.

YouTube Music personalised data (home feed, library, likes, history) requires a
signed-in Google account. Instead of a separate OAuth flow, we reuse the
Netscape cookie file that ``cookies_manager`` already extracts from the user's
browser. The parsing here mirrors ``service.js`` (``parseCookies``), including
giving youtube.com lines precedence and synthesising ``SAPISID`` from
``__Secure-3PAPISID`` when absent, so ytmusicapi can compute its SAPISIDHASH
``Authorization`` header per request.

Security: never log cookie values.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Cookie names that indicate a signed-in session (compared lowercased).
# Mirrors the AUTH_COOKIE_NAMES set used in cookies_manager.
AUTH_COOKIE_NAMES = {
    "sapisid",
    "__secure-3papisid",
    "login_info",
    "sid",
    "hsid",
    "ssid",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve_path(cookies_path):
    """Return an explicit path, else the app's default cookie file location."""
    if cookies_path:
        return cookies_path
    try:
        import cookies_manager

        return cookies_manager.get_default_browser_cookies_path()
    except Exception:
        return ""


def parse_netscape_cookies(cookies_path=None):
    """Parse a Netscape cookie file into an ordered ``{name: value}`` dict.

    youtube.com lines are processed last so they take precedence on duplicate
    names, and ``SAPISID`` is synthesised from ``__Secure-3PAPISID`` when
    absent, matching ``service.js``. Returns ``{}`` if the file is missing or
    unreadable.
    """
    path = _resolve_path(cookies_path)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        logger.debug("Could not read YouTube Music cookie file", exc_info=True)
        return {}

    lines = [
        line for line in text.split("\n") if line.strip() and not line.startswith("#")
    ]
    # Stable sort: youtube.com lines last so they overwrite earlier duplicates.
    lines.sort(key=lambda line: 1 if "youtube.com" in line else 0)

    cookie_map = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        name = parts[5].strip()
        value = parts[6].strip()
        if name:
            cookie_map[name] = value

    if "SAPISID" not in cookie_map and "__Secure-3PAPISID" in cookie_map:
        cookie_map["SAPISID"] = cookie_map["__Secure-3PAPISID"]

    return cookie_map


def _cookie_header(cookie_map):
    return "; ".join(f"{name}={value}" for name, value in cookie_map.items())


def is_authenticated(cookies_path=None):
    """True if the cookie file contains at least one auth cookie."""
    cookie_map = parse_netscape_cookies(cookies_path)
    return any(name.lower() in AUTH_COOKIE_NAMES for name in cookie_map)


def build_browser_headers(cookies_path=None):
    """Return a ytmusicapi browser-auth header dict, or ``None`` when signed out.

    The dict carries the ``Cookie`` header, the standard YouTube Music request
    headers, and a sentinel ``Authorization: SAPISIDHASH`` so ytmusicapi treats
    it as browser auth; ytmusicapi recomputes the real time-based SAPISIDHASH
    from the ``__Secure-3PAPISID`` cookie on each request. Returns ``None`` when
    no auth cookies are present (anonymous mode).
    """
    cookie_map = parse_netscape_cookies(cookies_path)
    if not any(name.lower() in AUTH_COOKIE_NAMES for name in cookie_map):
        return None
    cookie_header = _cookie_header(cookie_map)
    if not cookie_header:
        return None
    return {
        "Cookie": cookie_header,
        # ytmusicapi 1.x classifies headers as browser-auth only when an
        # Authorization header contains the literal "SAPISIDHASH"; it then
        # recomputes the real time-based hash from the cookie on every request.
        # (See ytmusicapi.auth.auth_parse.determine_auth_type.)
        "Authorization": "SAPISIDHASH",
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "X-Goog-AuthUser": "0",
        "x-origin": "https://music.youtube.com",
        "origin": "https://music.youtube.com",
    }
