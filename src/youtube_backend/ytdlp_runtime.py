"""yt-dlp loading and playback options."""

import importlib
import logging
import os
import sys
import threading
import zipfile
import zipimport

import paths
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend.pot_provider_service import pot_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


yt_dlp_module = None
YoutubeDL = None
_yt_dlp_load_lock = threading.Lock()


class InvalidYtDlpArchiveError(ImportError):
    pass


def _clear_yt_dlp_import_state(path):
    while path in sys.path:
        sys.path.remove(path)
    for module_name in list(sys.modules):
        if module_name == "yt_dlp" or module_name.startswith("yt_dlp."):
            del sys.modules[module_name]


def _is_corrupt_yt_dlp_error(exception):
    message = str(exception).lower()
    return isinstance(
        exception,
        (InvalidYtDlpArchiveError, zipfile.BadZipFile, zipimport.ZipImportError),
    ) or (
        "bad local file header" in message
        or "not a zip file" in message
        or "file is not a zip file" in message
        or "no module named 'yt_dlp'" in message
    )


def _discard_bad_yt_dlp(path, reason):
    _clear_yt_dlp_import_state(path)
    try:
        os.remove(path)
        logger.warning("Removed invalid yt-dlp archive at %s: %s", path, reason)
    except OSError as exc:
        logger.error("Failed to remove invalid yt-dlp archive at %s: %s", path, exc)


def _use_yt_dlp_module(module):
    global YoutubeDL, yt_dlp_module
    yt_dlp_module = module
    YoutubeDL = module.YoutubeDL
    return True


_extractor_warmup_lock = threading.Lock()
_extractors_warmed = False


def _warm_youtube_extractor():
    """Import the yt-dlp YouTube extractor once, single-threaded.

    yt-dlp resolves its (lazy) extractor classes on first use. The home-feed
    scraper fans out many worker threads that each trigger that first import at
    the same moment, and the concurrent partial initialization races, failing
    with a spurious ``ImportError: cannot import name '_EJS_WIKI_URL' ... most
    likely due to a circular import`` from ``_video.py`` — which breaks *all*
    extraction, not just the racing thread. Warming the import once behind a
    lock makes every later thread reuse the fully-initialized module.
    """
    global _extractors_warmed
    if _extractors_warmed:
        return
    with _extractor_warmup_lock:
        if _extractors_warmed:
            return
        try:
            importlib.import_module("yt_dlp.extractor.youtube._video")
        except Exception as exc:
            # A genuine failure will resurface on the real extract call; don't
            # wedge the flag so a later attempt can retry the import.
            logger.warning(f"yt-dlp YouTube extractor warmup failed: {exc}")
            return
        _extractors_warmed = True


def _loaded_from_path(module, path):
    module_file = os.path.abspath(getattr(module, "__file__", ""))
    expected_path = os.path.abspath(path)
    return module_file.lower().startswith(expected_path.lower())


def _load_yt_dlp_locked():
    global YoutubeDL, yt_dlp_module
    tried_paths = set()
    while os.path.exists(paths.yt_dlp_path) and paths.yt_dlp_path not in tried_paths:
        current_path = paths.yt_dlp_path
        tried_paths.add(current_path)
        if current_path.lower().endswith(".zip") and not zipfile.is_zipfile(
            current_path
        ):
            _discard_bad_yt_dlp(current_path, "not a valid zip file")
            paths.yt_dlp_path = paths._get_yt_dlp_path()
            continue
        try:
            _clear_yt_dlp_import_state(current_path)
            if current_path not in sys.path:
                sys.path.insert(0, current_path)
            import yt_dlp

            if not _loaded_from_path(yt_dlp, current_path):
                raise InvalidYtDlpArchiveError(
                    f"yt-dlp was loaded from an unexpected location: {yt_dlp.__file__}"
                )
            return _use_yt_dlp_module(yt_dlp)
        except Exception as e:
            logger.error(f"Failed to load yt-dlp from {current_path}: {e}")
            _clear_yt_dlp_import_state(current_path)
            yt_dlp_module = None
            YoutubeDL = None
            if _is_corrupt_yt_dlp_error(e):
                _discard_bad_yt_dlp(current_path, e)
                paths.yt_dlp_path = paths._get_yt_dlp_path()
                continue
            return False

    return False


def load_yt_dlp(force=False):
    """Import yt-dlp on demand (idempotent and thread-safe).

    yt-dlp is a large, slow import (~0.9s) that is not needed to show the home
    screen, so it is no longer imported at module load. The first consumer to
    need it — ``check_yt_dlp()``, the background warm thread started at app
    startup, or an explicit caller — triggers the load, and every later call
    returns immediately. ``force=True`` reloads even when a module is already
    loaded, so a freshly downloaded/updated archive takes effect in place.
    """
    if YoutubeDL is not None and not force:
        return True
    with _yt_dlp_load_lock:
        if YoutubeDL is not None and not force:
            return True
        return _load_yt_dlp_locked()


class YtDlpLogger:
    """Routes yt-dlp internal messages to Python standard logging."""

    def __init__(self, logger_instance=None):
        self._logger = logger_instance or logging.getLogger("yt_dlp")

    def debug(self, msg):
        # yt-dlp routes screen output and verbose '[debug]' lines to debug().
        # We log them as INFO so they are captured in log files and console.
        self._logger.info(msg)

    def info(self, msg):
        self._logger.info(msg)

    def warning(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)


PLAYER_OPTS = {
    "quiet": False,
    "verbose": True,
    "no_warnings": False,
    "logger": YtDlpLogger(),
    "noplaylist": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["default"],
            "js_variant": "main",
        }
    },
    "js_runtimes": {"deno": {}},
    "allowed_extractors": ["youtube", "youtube:.*"],
    "nocheckcertificate": True,
    "socket_timeout": 5,
    "cachedir": os.path.join(paths.settings_path, "cache", "yt-dlp"),
    "lazy_extractors": True,
}


def get_player_client_choices():
    return [
        ("default", _("الافتراضي المفضل لـ yt-dlp")),
        ("android", _("أندرويد (Android)")),
        ("web", _("الويب (Web)")),
        ("mweb", _("ويب الجوال (Mobile Web)")),
        ("ios", _("آي أو إس (iOS)")),
        ("tv", _("التلفزيون الذكي (Smart TV)")),
        ("tv_embedded", _("تلفزيون مضمن (TV Embedded)")),
        ("android_vr", _("أندرويد الواقع الافتراضي (Android VR)")),
        ("web_creator", _("استوديو الويب (Web Creator)")),
        ("web_safari", _("سفاري الويب (Web Safari)")),
    ]


AUTHED_INCOMPATIBLE_CLIENTS = {
    "android",
    "android_vr",
    "ios",
    "tv_simply",
    "web",
    "web_safari",
}


def get_configured_player_clients(client_override=None, has_cookies=None):
    """
    Returns the player client list to pass to yt-dlp extractor_args.
    If 'default' or not set, returns ['default'].
    If has_cookies is True (or cookiespath exists) and the requested client
    does not support cookies or fails with SABR streaming, automatically falls back to ['default'].
    Otherwise returns [client_name] or the provided client_override.
    """
    if has_cookies is None:
        cookies_path = config_get("cookiespath")
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))

    if client_override is not None:
        if isinstance(client_override, (list, tuple)):
            clients = list(client_override)
        elif isinstance(client_override, str) and client_override != "default":
            clients = [client_override]
        else:
            clients = ["default"]
    else:
        selected_client = config_get("player_client")
        if not selected_client or selected_client == "default":
            clients = ["default"]
        else:
            clients = [str(selected_client)]

    # Map legacy/alias client names if present
    clients = ["web_embedded" if c == "tv_embedded" else c for c in clients]

    if has_cookies and any(c in AUTHED_INCOMPATIBLE_CLIENTS for c in clients):
        logger.warning(
            "Player client(s) %s are incompatible with cookies or SABR streaming; falling back to 'default'",
            clients,
        )
        return ["default"]

    return clients


def get_configured_js_runtimes():
    runtimes = {}
    qjs_path = paths.get_quickjs_path()
    if qjs_path and os.path.exists(qjs_path):
        runtimes["quickjs"] = {"path": qjs_path}
    deno_path = paths.get_deno_path()
    if deno_path and os.path.isfile(deno_path):
        runtimes["deno"] = {"path": deno_path}
    elif not runtimes:
        runtimes["deno"] = {}
    return runtimes


def get_ydl_instance(client=None, cookies_path=None):
    """Returns a fresh YoutubeDL instance for thread-safe extraction."""
    if not YoutubeDL:
        return None
    # Force the (lazy) YouTube extractor import once before parallel scraper
    # threads race it into a spurious circular-import failure.
    _warm_youtube_extractor()
    has_cookies = bool(cookies_path and os.path.exists(cookies_path))
    clients = get_configured_player_clients(client, has_cookies=has_cookies)
    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = get_configured_js_runtimes()
    opts["extractor_args"] = {
        "youtube": {"player_client": clients, "js_variant": "main"}
    }
    if config_get("pot_provider_enabled"):
        try:
            pot_service.initialize()
            if (
                pot_service.ensure_started()
                and "youtubepot-bgutilhttp" not in opts["extractor_args"]
            ):
                opts["extractor_args"]["youtubepot-bgutilhttp"] = {
                    "base_url": [pot_service.get_base_url()]
                }
            if (
                pot_service.has_binary()
                and "youtubepot-bgutilcli" not in opts["extractor_args"]
            ):
                opts["extractor_args"]["youtubepot-bgutilcli"] = {
                    "cli_path": [paths.pot_provider_exe]
                }
        except Exception as e:
            logger.debug(f"Failed to inject POT provider args: {e}")
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    return YoutubeDL(opts)
