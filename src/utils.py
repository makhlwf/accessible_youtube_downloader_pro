import html as html_parser
import importlib
import json
import logging
import math
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
import zipimport
from collections import OrderedDict

import requests
import wx

import application
import paths
from database import WatchHistory
from deno_service import deno_service
from language_handler import _
from pot_provider_service import pot_service
from settings_handler import config_get
from youtube_url_utils import (  # noqa: F401
    extract_launch_youtube_url,
    extract_supported_youtube_url,
    is_supported_youtube_url,
    youtube_regexp,
)

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


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "like", "liked"}
    return bool(value)


def _coerce_count(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if not math.isnan(value) else None

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"([\d,.]+)\s*([kmb])?", text, re.IGNORECASE)
    if not match:
        return None

    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None

    suffix = (match.group(2) or "").lower()
    multiplier = {"k": 1000, "m": 1000000, "b": 1000000000}.get(suffix, 1)
    return round(number * multiplier)


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


def _normalize_like_info(result):
    if not isinstance(result, dict) or "error" in result:
        return {
            "likes": None,
            "rating": None,
            "is_liked": False,
            "is_disliked": False,
        }

    rating = result.get("rating")
    is_liked = _coerce_bool(result.get("is_liked"))
    is_disliked = _coerce_bool(result.get("is_disliked"))

    if rating not in {"like", "dislike"}:
        if is_liked:
            rating = "like"
        elif is_disliked:
            rating = "dislike"
        else:
            rating = None

    likes = _coerce_count(result.get("likes"))
    if likes is None:
        likes = _coerce_count(result.get("like_count"))

    return {
        "likes": likes,
        "rating": rating,
        "is_liked": rating == "like",
        "is_disliked": rating == "dislike",
    }


def _chapter_time_ms(chapter):
    for key in (
        "time_ms",
        "time_range_start_millis",
        "timeRangeStartMillis",
        "start_millis",
        "startMillis",
        "start_time_ms",
    ):
        if key in chapter and chapter[key] is not None:
            try:
                return max(0, int(float(chapter[key])))
            except TypeError, ValueError:
                continue

    for key in ("start_time", "startTime"):
        if key in chapter and chapter[key] is not None:
            try:
                return max(0, int(float(chapter[key]) * 1000))
            except TypeError, ValueError:
                continue

    return None


def _normalize_video_chapters(value):
    if isinstance(value, dict):
        value = value.get("chapters", [])
    if not isinstance(value, list):
        return []

    chapters = []
    for chapter in value:
        if not isinstance(chapter, dict):
            continue
        time_ms = _chapter_time_ms(chapter)
        if time_ms is None:
            continue
        title = str(chapter.get("title") or _("فصل بدون عنوان")).strip()
        chapters.append({"title": title, "time_ms": time_ms})

    chapters.sort(key=lambda chapter: chapter["time_ms"])
    normalized = []
    seen = set()
    for chapter in chapters:
        key = (chapter["time_ms"], chapter["title"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(chapter)
    return normalized


SUBTITLE_EXT_PRIORITY = {
    "json3": 0,
    "vtt": 1,
    "webvtt": 1,
    "ttml": 2,
    "dfxp": 2,
    "srv3": 3,
    "srv2": 4,
    "srv1": 5,
}


def _clean_subtitle_text(value):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_parser.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _subtitle_track_priority(entry):
    ext = str(entry.get("ext") or "").lower()
    return SUBTITLE_EXT_PRIORITY.get(ext, 99)


def _subtitle_language_label(code, entries, source):
    names = []
    for entry in entries:
        name = str(
            entry.get("name")
            or entry.get("language")
            or entry.get("language_name")
            or ""
        ).strip()
        if name and name not in names:
            names.append(name)

    label = names[0] if names else code
    if code and code not in label:
        label = f"{label} ({code})"
    if source == "automatic":
        label = _("{} - تلقائي").format(label)
    return label


def _normalize_subtitle_tracks(info):
    if not isinstance(info, dict):
        return []

    tracks = []
    seen_codes = set()
    sources = (
        ("manual", info.get("subtitles") or {}),
        ("automatic", info.get("automatic_captions") or {}),
    )

    for source, subtitles in sources:
        if not isinstance(subtitles, dict):
            continue
        for code, entries in subtitles.items():
            code = str(code or "").strip()
            if not code or code in seen_codes:
                continue
            if isinstance(entries, dict):
                entries = [entries]
            if not isinstance(entries, list):
                continue
            entries = [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("url")
            ]
            if not entries:
                continue

            selected = min(entries, key=_subtitle_track_priority)
            tracks.append(
                {
                    "code": code,
                    "label": _subtitle_language_label(code, entries, source),
                    "url": selected.get("url"),
                    "ext": str(selected.get("ext") or "").lower(),
                    "source": source,
                }
            )
            seen_codes.add(code)

    return sorted(tracks, key=lambda track: track["label"].casefold())


def _parse_subtitle_timestamp(value, numeric_unit="seconds"):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("ms"):
            return max(0, int(float(text[:-2]) or 0))
        if text.endswith("s") and not text.endswith("ms"):
            return max(0, int((float(text[:-1]) or 0) * 1000))
        if ":" in text:
            match = re.match(
                r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?",
                text,
            )
            if not match:
                return None
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            milliseconds = int((match.group(4) or "0").ljust(3, "0")[:3])
            return ((hours * 3600 + minutes * 60 + seconds) * 1000) + milliseconds

        number = float(text)
        if numeric_unit == "milliseconds":
            return max(0, int(number))
        return max(0, int(number * 1000))
    except TypeError, ValueError:
        return None


def _normalize_subtitle_cues(cues):
    normalized = []
    for cue in cues:
        text = _clean_subtitle_text(cue.get("text"))
        if not text:
            continue
        try:
            start_ms = int(cue.get("start_ms"))
            end_ms = int(cue.get("end_ms"))
        except TypeError, ValueError:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 1500
        normalized.append(
            {"start_ms": max(0, start_ms), "end_ms": max(0, end_ms), "text": text}
        )

    normalized.sort(key=lambda cue: (cue["start_ms"], cue["end_ms"]))
    deduped = []
    seen = set()
    for cue in normalized:
        key = (cue["start_ms"], cue["end_ms"], cue["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cue)
    return deduped


def _parse_json3_subtitles(text):
    try:
        data = json.loads(text)
    except TypeError, json.JSONDecodeError:
        return []

    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return []

    cues = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        segments = event.get("segs") or []
        if not segments:
            continue
        text = "".join(str(segment.get("utf8") or "") for segment in segments)
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs")
        try:
            start_ms = int(start_ms)
        except TypeError, ValueError:
            continue
        try:
            end_ms = start_ms + int(duration_ms)
        except TypeError, ValueError:
            next_start = None
            for next_event in events[index + 1 :]:
                if isinstance(next_event, dict) and next_event.get("tStartMs"):
                    try:
                        next_start = int(next_event["tStartMs"])
                    except TypeError, ValueError:
                        next_start = None
                    break
            end_ms = next_start if next_start is not None else start_ms + 1500
        cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
    return _normalize_subtitle_cues(cues)


def _parse_vtt_subtitles(text):
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue

        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue

        timing = lines[timing_index]
        start_text, end_text = [part.strip() for part in timing.split("-->", 1)]
        end_text = end_text.split()[0] if end_text else ""
        start_ms = _parse_subtitle_timestamp(start_text)
        end_ms = _parse_subtitle_timestamp(end_text)
        if start_ms is None or end_ms is None:
            continue
        cues.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": " ".join(lines[timing_index + 1 :]),
            }
        )
    return _normalize_subtitle_cues(cues)


def _parse_xml_subtitles(text):
    try:
        root = ET.fromstring(str(text or ""))
    except ET.ParseError:
        return []

    cues = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"p", "text"}:
            continue
        content = "".join(element.itertext())
        if tag == "text":
            start_ms = _parse_subtitle_timestamp(
                element.get("start"), numeric_unit="seconds"
            )
            duration_ms = _parse_subtitle_timestamp(
                element.get("dur"), numeric_unit="seconds"
            )
            end_ms = (
                start_ms + duration_ms if None not in (start_ms, duration_ms) else None
            )
        else:
            start_ms = _parse_subtitle_timestamp(
                element.get("begin") or element.get("t"),
                numeric_unit="milliseconds" if element.get("t") else "seconds",
            )
            end_ms = _parse_subtitle_timestamp(element.get("end"))
            duration_ms = _parse_subtitle_timestamp(
                element.get("dur") or element.get("d"),
                numeric_unit="milliseconds" if element.get("d") else "seconds",
            )
            if end_ms is None and None not in (start_ms, duration_ms):
                end_ms = start_ms + duration_ms
        if start_ms is None or end_ms is None:
            continue
        cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": content})
    return _normalize_subtitle_cues(cues)


def _parse_subtitle_cues(text, ext):
    ext = str(ext or "").lower()
    if ext == "json3":
        return _parse_json3_subtitles(text)
    if ext in {"vtt", "webvtt"}:
        return _parse_vtt_subtitles(text)
    if ext in {"ttml", "dfxp", "srv1", "srv2", "srv3"}:
        return _parse_xml_subtitles(text)
    return (
        _parse_vtt_subtitles(text)
        or _parse_json3_subtitles(text)
        or _parse_xml_subtitles(text)
    )


class InfoCache:
    def __init__(self, default_ttl=300, maxsize=256):
        self.cache = OrderedDict()
        self.default_ttl = default_ttl
        self.maxsize = maxsize
        self.lock = threading.Lock()

    def get(self, url, ttl=None):
        if ttl is None:
            ttl = self.default_ttl
        with self.lock:
            if url in self.cache:
                info, timestamp = self.cache[url]
                if time.time() - timestamp < ttl:
                    self.cache.move_to_end(url)
                    return info
                else:
                    del self.cache[url]
        return None

    def set(self, url, info):
        with self.lock:
            now = time.time()
            if url in self.cache:
                self.cache.move_to_end(url)
            self.cache[url] = (info, now)
            while len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    def clear(self):
        with self.lock:
            self.cache.clear()


_info_cache = InfoCache(maxsize=256, default_ttl=3600)
_stream_cache = InfoCache(maxsize=256, default_ttl=1200)
_subtitle_cues_cache = InfoCache(maxsize=128, default_ttl=3600)
_stream_inflight = {}
_stream_inflight_lock = threading.Lock()


yt_dlp_module = None
YoutubeDL = None


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


def _loaded_from_path(module, path):
    module_file = os.path.abspath(getattr(module, "__file__", ""))
    expected_path = os.path.abspath(path)
    return module_file.lower().startswith(expected_path.lower())


def load_yt_dlp():
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


load_yt_dlp()


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

YOUTUBEI_PACKAGE = "youtubei.js"
YOUTUBEI_IMPORT_SPECIFIER = "youtubei.js"


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


def get_ydl_instance(client=None, cookies_path=None):
    """Returns a fresh YoutubeDL instance for thread-safe extraction."""
    if not YoutubeDL:
        return None
    has_cookies = bool(cookies_path and os.path.exists(cookies_path))
    clients = get_configured_player_clients(client, has_cookies=has_cookies)
    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
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


VIDEO_QUALITIES = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_QUALITIES = [64, 128, 256]

VIDEO_QUALITY_DESCRIPTIONS = {
    144: _("144ب (جودة منخفضة جدًا)"),
    240: _("240ب (جودة منخفضة)"),
    360: _("360ب (جودة متوسطة)"),
    480: _("480ب (جودة متوسطة)"),
    720: _("720ب (جودة عالية عالية الدقة)"),
    1080: _("1080ب (جودة عالية جدًا عالية الدقة الكاملة)"),
    1440: _("1440ب (جودة فائقة 2 كي)"),
    2160: _("2160ب (جودة فائقة 4 كي)"),
}


def get_quality_description(height):
    return VIDEO_QUALITY_DESCRIPTIONS.get(
        height, _("{}ب (جودة غير معروفة)").format(height)
    )


def get_audio_track_languages():
    return [
        ("ar", _("العربية")),
        ("en", _("الإنجليزية")),
        ("es", _("الإسبانية")),
        ("fr", _("الفرنسية")),
        ("de", _("الألمانية")),
        ("it", _("الإيطالية")),
        ("pt", _("البرتغالية")),
        ("ru", _("الروسية")),
        ("ja", _("اليابانية")),
        ("ko", _("الكورية")),
        ("hi", _("الهندية")),
        ("tr", _("التركية")),
        ("id", _("الإندونيسية")),
        ("zh", _("الصينية")),
        ("vi", _("الفيتنامية")),
        ("bn", _("البنغالية")),
        ("pl", _("البولندية")),
        ("th", _("التايلاندية")),
        ("nl", _("الهولندية")),
        ("sv", _("السويدية")),
        ("fa", _("الفارسية")),
        ("ur", _("الأردية")),
    ]


AUDIO_TRACK_LANGUAGES = [
    ("ar", "العربية"),
    ("en", "الإنجليزية"),
    ("es", "الإسبانية"),
    ("fr", "الفرنسية"),
    ("de", "الألمانية"),
    ("it", "الإيطالية"),
    ("pt", "البرتغالية"),
    ("ru", "الروسية"),
    ("ja", "اليابانية"),
    ("ko", "الكورية"),
    ("hi", "الهندية"),
    ("tr", "التركية"),
    ("id", "الإندونيسية"),
    ("zh", "الصينية"),
    ("vi", "الفيتنامية"),
    ("bn", "البنغالية"),
    ("pl", "البولندية"),
    ("th", "التايلاندية"),
    ("nl", "الهولندية"),
    ("sv", "السويدية"),
    ("fa", "الفارسية"),
    ("ur", "الأردية"),
]


def is_language_match(track_lang, target_lang):
    if not track_lang or not target_lang:
        return False
    tl = str(track_lang).strip().lower()
    tgt = str(target_lang).strip().lower()
    if tl == tgt:
        return True
    tl_base = tl.split("-")[0].split("_")[0]
    tgt_base = tgt.split("-")[0].split("_")[0]
    if tl_base == tgt_base:
        return True
    iso_map = {
        "eng": "en",
        "ara": "ar",
        "spa": "es",
        "fra": "fr",
        "fre": "fr",
        "deu": "de",
        "ger": "de",
        "ita": "it",
        "por": "pt",
        "rus": "ru",
        "jpn": "ja",
        "kor": "ko",
        "hin": "hi",
        "tur": "tr",
        "ind": "id",
        "zho": "zh",
        "chi": "zh",
        "vie": "vi",
        "ben": "bn",
        "pol": "pl",
        "tha": "th",
        "nld": "nl",
        "dut": "nl",
        "swe": "sv",
        "fas": "fa",
        "per": "fa",
        "urd": "ur",
    }
    tl_mapped = iso_map.get(tl_base, tl_base)
    tgt_mapped = iso_map.get(tgt_base, tgt_base)
    return tl_mapped == tgt_mapped


def get_language_display_name(lang_code, note=""):
    code_base = (lang_code or "").split("-")[0].split("_")[0].lower()
    for code, label in get_audio_track_languages():
        if code.lower() == code_base:
            return label
    if note:
        cleaned_note = str(note).split("-")[0].split("(")[0].split(",")[0].strip()
        if cleaned_note and not cleaned_note.isdigit() and len(cleaned_note) > 1:
            return cleaned_note
    if lang_code and lang_code != "und":
        return str(lang_code).upper()
    return _("الصوت الأصلي")


def download_yt_dlp(parent=None):
    from gui.update_dialog import UpdateDialog

    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    os.makedirs(paths.settings_path, exist_ok=True)
    target_path = os.path.join(paths.settings_path, "yt_dlp.zip")
    download_path = f"{target_path}.download"
    try:
        if os.path.exists(download_path):
            os.remove(download_path)
    except OSError:
        pass

    UpdateDialog(
        parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        url,
        download_path,
        _("جاري تنزيل واي تي دي إل بي"),
    )

    if os.path.exists(download_path):
        if zipfile.is_zipfile(download_path):
            os.replace(download_path, target_path)
        else:
            try:
                os.remove(download_path)
            except OSError:
                pass
            show_error(_("ملف واي تي دي إل بي الذي تم تنزيله غير صالح"))

    paths.yt_dlp_path = (
        target_path if os.path.exists(target_path) else paths._get_yt_dlp_path()
    )
    load_yt_dlp()


def get_latest_github_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("tag_name")
    except Exception as e:
        logger.error(f"Failed to get latest release for {repo}: {e}")
    return None


def get_latest_npm_package_version(package):
    url = f"https://registry.npmjs.org/{package}/latest"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("version")
    except Exception as e:
        logger.error(f"Failed to get latest npm version for {package}: {e}")
    return None


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return None


def _version_from_youtubei_specifier(specifier):
    if not specifier:
        return None
    match = re.search(r"(?:npm:)?youtubei\.js@([^\s\"',}]+)", str(specifier))
    if not match:
        return None
    version = match.group(1).strip()
    return version.lstrip("^~<>= ")


def _read_youtubei_lock_version(lock_path):
    data = _read_json_file(lock_path)
    if not isinstance(data, dict):
        return None

    npm_entries = data.get("npm", {})
    if isinstance(npm_entries, dict):
        for name in npm_entries:
            match = re.fullmatch(r"youtubei\.js@(.+)", name)
            if match:
                return match.group(1)

    specifiers = data.get("specifiers", {})
    if isinstance(specifiers, dict):
        for key, value in specifiers.items():
            if str(key).startswith("npm:youtubei.js@"):
                version = str(value).strip()
                if version:
                    return version

    return None


def _read_youtubei_config_version(config_path):
    data = _read_json_file(config_path)
    if not isinstance(data, dict):
        return None

    imports = data.get("imports", {})
    if not isinstance(imports, dict):
        return None
    return _version_from_youtubei_specifier(imports.get(YOUTUBEI_IMPORT_SPECIFIER))


def get_youtubei_version():
    version = _read_youtubei_lock_version(paths.get_js_runtime_lock_path())
    if version:
        return version
    return _read_youtubei_config_version(paths.get_js_runtime_config_path())


def _semver_key(version):
    match = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(version or ""))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _is_newer_version(latest, current):
    if not latest:
        return False
    if not current:
        return True
    latest_key = _semver_key(latest)
    current_key = _semver_key(current)
    if latest_key and current_key:
        return latest_key > current_key
    return latest != current


def _write_youtubei_runtime_config(version):
    config_path = paths.get_writable_js_runtime_file("deno.json")
    config = {
        "imports": {YOUTUBEI_IMPORT_SPECIFIER: f"npm:{YOUTUBEI_PACKAGE}@{version}"}
    }
    temp_path = f"{config_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp_path, config_path)
    return config_path


def _deno_cache_command(config_path, lock_path, reload_package=False):
    command = [
        paths.get_deno_path(),
        "cache",
        "--config",
        config_path,
        "--lock",
        lock_path,
    ]
    if reload_package:
        command.append(f"--reload=npm:{YOUTUBEI_PACKAGE}")
    command.append(paths.get_js_runtime_service_script())
    return command


def _run_deno_cache(config_path, lock_path, reload_package=False):
    env = os.environ.copy()
    env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        _deno_cache_command(config_path, lock_path, reload_package=reload_package),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        env=env,
        cwd=paths.main_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )


def install_youtubei_version(version, parent=None, success_message=None):
    if not os.path.exists(paths.get_deno_path()):
        show_error(
            _(
                "لم يتم العثور على أداة deno.exe, وهي مطلوبة لتحديث مكتبة YouTube.js (Innertube)."
            ),
            parent=parent,
        )
        return False

    try:
        config_path = _write_youtubei_runtime_config(version)
        lock_path = paths.get_writable_js_runtime_file("deno.lock")
        result = _run_deno_cache(config_path, lock_path, reload_package=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            show_error(
                _("تعذر تحديث مكتبة YouTube.js (Innertube)"),
                Exception(detail),
                parent=parent,
            )
            return False

        deno_service.stop()
        wx.MessageBox(
            success_message
            or _("تم تحديث مكتبة YouTube.js (Innertube) إلى الإصدار {}").format(
                version
            ),
            _("اكتمل التحديث"),
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        return True
    except Exception as e:
        show_error(_("تعذر تحديث مكتبة YouTube.js (Innertube)"), e, parent=parent)
        return False


def update_youtubei(parent=None):
    current = get_youtubei_version()
    latest = get_latest_npm_package_version(YOUTUBEI_PACKAGE)
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات تحديث مكتبة YouTube.js (Innertube) من npm"),
            parent=parent,
        )
        return False

    if not _is_newer_version(latest, current):
        wx.MessageBox(
            _(
                "أنت تستخدم بالفعل أحدث إصدار من مكتبة YouTube.js (Innertube) ({})"
            ).format(current or latest),
            _("لا يوجد تحديث"),
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        return True

    msg = wx.MessageBox(
        _(
            "هناك إصدار جديد متوفر من مكتبة YouTube.js (Innertube)\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
        ).format(current or _("غير معروف"), latest),
        _("تحديث متوفر"),
        style=wx.YES_NO | wx.ICON_INFORMATION,
        parent=parent or wx.GetApp().GetTopWindow(),
    )
    if msg == wx.YES:
        return install_youtubei_version(latest, parent=parent)
    return False


def refresh_youtubei_cache(parent=None):
    version = get_youtubei_version()
    if not version:
        show_error(
            _("تعذر تحديد إصدار مكتبة YouTube.js (Innertube) الحالي"),
            parent=parent,
        )
        return False
    return install_youtubei_version(
        version,
        parent=parent,
        success_message=_("تم تحديث ذاكرة مكتبة YouTube.js (Innertube) المؤقتة"),
    )


def get_yt_dlp_version():
    if yt_dlp_module:
        try:
            if hasattr(yt_dlp_module, "version"):
                return getattr(yt_dlp_module.version, "__version__", None)
            return getattr(yt_dlp_module, "__version__", None)
        except Exception:
            pass
    return None


def update_yt_dlp():
    current = get_yt_dlp_version()
    latest = get_latest_github_release("yt-dlp/yt-dlp")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من واي تي دي إل بي ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من واي تي دي إل بي\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()


def _deno_release_asset():
    machine = platform.machine().lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    target = {"win32": "pc-windows-msvc", "linux": "unknown-linux-gnu"}.get(
        sys.platform
    )
    if not arch or not target:
        raise RuntimeError(f"Unsupported Deno platform: {sys.platform}/{machine}")
    return f"deno-{arch}-{target}.zip"


def download_deno(parent=None):
    from gui.update_dialog import UpdateDialog

    url = f"https://github.com/denoland/deno/releases/latest/download/{_deno_release_asset()}"
    install_dir = os.path.dirname(paths.deno_install_path)
    os.makedirs(install_dir, exist_ok=True)
    UpdateDialog(
        parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        url,
        os.path.join(install_dir, "deno.zip"),
        _("جاري تنزيل دينو"),
        is_zip=True,
    )


def get_deno_version():
    if not os.path.exists(paths.get_deno_path()):
        return None
    try:
        result = subprocess.run(
            [paths.get_deno_path(), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=False,
        )
        if result.returncode == 0:
            line = result.stdout.splitlines()[0]
            version = line.split(" ")[1]
            if not version.startswith("v"):
                version = "v" + version
            return version
    except Exception:
        pass
    return None


def update_deno():
    current = get_deno_version()
    latest = get_latest_github_release("denoland/deno")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من دينو ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من دينو\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_deno()


def check_yt_dlp(parent=None):
    if not YoutubeDL:
        msg = wx.MessageBox(
            _("لم يتم العثور على مكتبة واي تي دي إل بي, هل تريد تنزيلها الآن؟"),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()
            return YoutubeDL is not None
        return False
    return True


def check_deno(parent=None):
    if not os.path.exists(paths.get_deno_path()):
        msg = wx.MessageBox(
            _(
                "لم يتم العثور على أداة deno.exe, وهي مطلوبة لبعض وظائف اليوتيوب. هل تريد تنزيلها الآن؟"
            ),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_deno()
            return os.path.exists(paths.get_deno_path())
        return False
    return True


def get_pot_provider_version():
    """Returns the installed version string of bgutil-pot, or None if not installed."""
    return pot_service.get_installed_version()


def update_pot_provider(parent=None):
    """Checks for bgutil-pot updates on GitHub and prompts the user to download if newer."""
    current = get_pot_provider_version()
    latest = get_latest_github_release("jim60105/bgutil-ytdlp-pot-provider-rs")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        return False

    if (current or "").lstrip("v") == (latest or "").lstrip("v"):
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من مولد رموز POT ({})").format(current),
            _("لا يوجد تحديث"),
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        return False
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من مولد رموز POT\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        if msg == wx.YES:
            return pot_service.download_and_install(parent=parent)
        return False


def check_pot_provider(parent=None):
    """Ensures bgutil-pot is installed and running if enabled, prompting download if missing."""
    if not config_get("pot_provider_enabled"):
        return False
    if not pot_service.is_installed():
        msg = wx.MessageBox(
            _(
                "لم يتم العثور على أداة مولد رموز POT (bgutil-pot)، وهي تساعد في حل قيود يوتيوب وتحسين التنزيل. هل تريد تنزيلها الآن؟"
            ),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        if msg == wx.YES:
            return pot_service.download_and_install(parent=parent)
        return False
    pot_service.ensure_started()
    return True


def ensure_deno_installed(parent=None, feature_name=None, **kwargs):
    """
    Checks if deno.exe is installed. If missing, prompts the user to download Deno.
    Returns True if Deno is available or installed, False otherwise.
    """
    if not os.path.exists(paths.get_deno_path()):
        feature = feature_name or kwargs.get("feature_name_ar") or _("هذه الميزة")
        msg_text = _(
            "تنبيه: لم يتم تثبيت أداة Deno وهي مطلوبة لـ {}. هل تريد تنزيل وتثبيت Deno الآن؟"
        ).format(feature)
        title = _("تنبيه")
        dialog_parent = parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None)
        res = wx.MessageBox(
            msg_text,
            title,
            style=wx.YES_NO | wx.ICON_WARNING,
            parent=dialog_parent,
        )
        if res == wx.YES:
            download_deno(dialog_parent)
            return os.path.exists(paths.get_deno_path())
        return False
    return True


def ensure_cookies_configured(parent=None, feature_name=None, **kwargs):
    """
    Checks if YouTube cookies file path is configured and exists.
    If missing, alerts user that cookies file is required in Settings.
    Returns True if valid, False otherwise.
    """
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        feature = feature_name or kwargs.get("feature_name_ar") or _("هذه الميزة")
        msg_text = _(
            "تنبيه: لم يتم تحديد ملف الكوكيز الخاص بيوتيوب أو أن الملف غير موجود. تتطلب هذه الميزة ({}) ملف كوكيز صالح. يرجى إضافة ملف كوكيز من إعدادات البرنامج."
        ).format(feature)
        title = _("تنبيه")
        dialog_parent = parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None)
        wx.MessageBox(
            msg_text,
            title,
            style=wx.OK | wx.ICON_WARNING,
            parent=dialog_parent,
        )
        return False
    return True


def ensure_js_dependencies():
    """Silently ensure JavaScript dependencies are cached by Deno."""
    if not os.path.exists(paths.get_deno_path()):
        return

    service_script = paths.get_js_runtime_service_script()
    config_path = paths.get_js_runtime_config_path()
    lock_path = paths.get_js_runtime_lock_path()

    if not os.path.exists(service_script) or not os.path.exists(config_path):
        return

    def _cache_task():
        try:
            if os.path.exists(lock_path):
                _run_deno_cache(config_path, lock_path)
            else:
                env = os.environ.copy()
                env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
                subprocess.run(
                    [
                        paths.get_deno_path(),
                        "cache",
                        "--config",
                        config_path,
                        service_script,
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                    env=env,
                    cwd=paths.main_path,
                    check=False,
                )
        except Exception:
            pass

    import threading

    threading.Thread(target=_cache_task, daemon=True).start()


def prefetch_dns():
    """Warms up the DNS cache for common YouTube video host patterns."""
    hosts = [
        "www.youtube.com",
        "m.youtube.com",
        "i.ytimg.com",
        "yt3.ggpht.com",
        "googlevideo.com",
    ]
    for host in hosts:
        try:
            threading.Thread(
                target=socket.gethostbyname, args=(host,), daemon=True
            ).start()
        except Exception:
            pass


prefetch_dns()


def get_audio_tracks_from_formats(formats, entry=None):
    if not formats:
        return []
    audio_formats = [
        f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"
    ]
    if not audio_formats:
        audio_formats = [f for f in formats if f.get("acodec") != "none"]
    if not audio_formats:
        return []

    tracks_by_key = OrderedDict()
    entry_lang = (entry.get("language") if isinstance(entry, dict) else "") or ""

    for f in audio_formats:
        lang = f.get("language") or ""
        note = str(f.get("format_note", ""))
        pref = f.get("language_preference")
        is_orig = (
            (pref is not None and pref > 0)
            or "original" in note.lower()
            or f.get("is_original") is True
            or (bool(entry_lang) and is_language_match(lang, entry_lang))
        )
        key = lang if lang else "default"
        if key not in tracks_by_key:
            tracks_by_key[key] = {
                "id": key,
                "lang": lang or "und",
                "is_original": is_orig,
                "formats": [f],
                "note": note,
            }
        else:
            tracks_by_key[key]["formats"].append(f)
            if is_orig:
                tracks_by_key[key]["is_original"] = True

    has_orig = any(tr["is_original"] for tr in tracks_by_key.values())
    if not has_orig and tracks_by_key:
        first_key = next(iter(tracks_by_key))
        tracks_by_key[first_key]["is_original"] = True

    tracks = []
    for key, tr in tracks_by_key.items():
        name = get_language_display_name(tr["lang"], tr["note"])
        if tr["is_original"]:
            if len(tracks_by_key) > 1 and name != _("الصوت الأصلي"):
                label = _("{language} (أصلي)").format(language=name)
            else:
                label = _("الصوت الأصلي")
        else:
            label = name
        tr["name"] = name
        tr["label"] = label
        tracks.append(tr)

    return tracks


def select_audio_format(
    formats,
    entry=None,
    preferred_lang=None,
    force_original=None,
    preferred_quality_index=None,
    audio_track_id=None,
):
    if not formats:
        return None, None

    tracks = get_audio_tracks_from_formats(formats, entry=entry)
    if not tracks:
        return None, None

    if preferred_quality_index is None:
        try:
            preferred_quality_index = int(config_get("defaultaudioquality"))
        except Exception:
            preferred_quality_index = 1

    target_abr = AUDIO_QUALITIES[min(preferred_quality_index, len(AUDIO_QUALITIES) - 1)]

    if audio_track_id:
        chosen_track = next((t for t in tracks if t["id"] == audio_track_id), None)
        if chosen_track:
            fmts = chosen_track["formats"]
            fmts_with_abr = [f for f in fmts if f.get("abr") is not None]
            best_fmt = (
                min(fmts_with_abr, key=lambda x: abs((x.get("abr") or 0) - target_abr))
                if fmts_with_abr
                else fmts[-1]
            )
            return best_fmt, chosen_track

    if force_original is None:
        force_original = bool(config_get("force_original_audio"))
    if preferred_lang is None:
        preferred_lang = config_get("preferred_audio_language")

    orig_track = next((t for t in tracks if t["is_original"]), tracks[0])

    if force_original:
        chosen_track = orig_track
    elif preferred_lang:
        matched_track = next(
            (t for t in tracks if is_language_match(t["lang"], preferred_lang)),
            None,
        )
        if matched_track:
            chosen_track = matched_track
        else:
            chosen_track = orig_track
    else:
        chosen_track = orig_track

    fmts = chosen_track["formats"]
    fmts_with_abr = [f for f in fmts if f.get("abr") is not None]
    best_fmt = (
        min(fmts_with_abr, key=lambda x: abs((x.get("abr") or 0) - target_abr))
        if fmts_with_abr
        else fmts[-1]
    )
    return best_fmt, chosen_track


def get_available_audio_tracks(url, audio_mode=False):
    info = get_media_info(url)
    if not info:
        return []
    formats = info.get("formats", [])
    tracks = get_audio_tracks_from_formats(formats, entry=info)
    if not tracks:
        return []

    try:
        preferred_audio_idx = int(config_get("defaultaudioquality"))
    except Exception:
        preferred_audio_idx = 1
    target_abr = AUDIO_QUALITIES[min(preferred_audio_idx, len(AUDIO_QUALITIES) - 1)]

    for track in tracks:
        fmts = track["formats"]
        fmts_with_abr = [f for f in fmts if f.get("abr") is not None]
        if fmts_with_abr:
            best_fmt = min(
                fmts_with_abr, key=lambda x: abs((x.get("abr") or 0) - target_abr)
            )
        else:
            best_fmt = fmts[-1]
        track["url"] = best_fmt.get("url")
        track["format_id"] = best_fmt.get("format_id")
        track["abr"] = best_fmt.get("abr")

    return tracks


def pick_best_format(
    formats,
    preferred_index,
    is_video=True,
    target_height=None,
    preferred_audio_lang=None,
    force_original=None,
    audio_track_id=None,
):
    if is_video:
        target_list = VIDEO_QUALITIES
        if target_height is not None:
            preferred_val = target_height
        else:
            preferred_val = target_list[preferred_index]

        available = [
            f
            for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]

        if not available:
            return None, None

        available.sort(key=lambda x: x.get("height", 0))

        fmt = None
        if target_height is not None:
            match = [f for f in available if f.get("height") == target_height]
            if match:
                fmt = match[0]

        if not fmt:
            try:
                pref_idx = (
                    target_list.index(preferred_val)
                    if target_height is None
                    else next(
                        i
                        for i, v in enumerate(target_list)
                        if v >= preferred_val or i == len(target_list) - 1
                    )
                )
            except ValueError, StopIteration:
                pref_idx = preferred_index

            for i in range(pref_idx, -1, -1):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        if not fmt:
            for i in range(pref_idx + 1, len(target_list)):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        if not fmt:
            fmt = available[-1]

        audio_fmt = None
        if fmt.get("acodec") == "none":
            audio_fmt, chosen_track = select_audio_format(
                formats,
                preferred_lang=preferred_audio_lang,
                force_original=force_original,
                audio_track_id=audio_track_id,
            )
            if audio_fmt is None:
                audio_formats = [
                    f
                    for f in formats
                    if f.get("acodec") != "none" and f.get("vcodec") == "none"
                ]
                if audio_formats:
                    audio_formats.sort(key=lambda x: x.get("abr") or 0)
                    audio_fmt = audio_formats[-1]
            elif chosen_track is not None:
                audio_fmt["_chosen_track"] = chosen_track

        return fmt, audio_fmt, fmt.get("height")
    else:
        fmt, chosen_track = select_audio_format(
            formats,
            preferred_lang=preferred_audio_lang,
            force_original=force_original,
            preferred_quality_index=preferred_index,
            audio_track_id=audio_track_id,
        )
        if fmt is not None:
            if chosen_track is not None:
                fmt["_chosen_track"] = chosen_track
            return fmt, None, fmt.get("abr")

        available = [
            f
            for f in formats
            if f.get("acodec") != "none"
            and f.get("vcodec") == "none"
            and f.get("abr") is not None
        ]
        if not available:
            available = [f for f in formats if f.get("acodec") != "none"]
        if not available:
            return None, None, None

        available.sort(key=lambda x: x.get("abr") or 0)
        target_abr = AUDIO_QUALITIES[min(preferred_index, len(AUDIO_QUALITIES) - 1)]

        # Find the format with abr closest to target_abr
        fmt = min(available, key=lambda x: abs((x.get("abr") or 0) - target_abr))

        return fmt, None, fmt.get("abr")


class Stream:
    def __init__(
        self,
        title,
        url,
        headers=None,
        audio_url=None,
        quality=None,
        webpage_url="",
        channel_name="",
        channel_url="",
        view_count=None,
        upload_date="",
        sponsorblock_segments=None,
        audio_track_id=None,
        audio_track_lang=None,
        audio_track_label=None,
    ):
        self.title = title
        self.url = url
        self.headers = headers or {}
        self.audio_url = audio_url
        self.quality = quality
        self.webpage_url = webpage_url
        self.channel_name = channel_name
        self.channel_url = channel_url
        self.view_count = view_count
        self.upload_date = upload_date
        self.sponsorblock_segments = sponsorblock_segments
        self.audio_track_id = audio_track_id
        self.audio_track_lang = audio_track_lang
        self.audio_track_label = audio_track_label


def _attach_sponsorblock_segments(stream, url):
    if (
        stream is not None
        and config_get("sponsorblock")
        and getattr(stream, "sponsorblock_segments", None) is None
    ):
        try:
            from sponsorblock_handler import get_sponsorblock_segments

            stream.sponsorblock_segments = get_sponsorblock_segments(url)
        except Exception:
            logger.debug("Failed to attach SponsorBlock segments", exc_info=True)
    return stream


def _stream_from_info(
    entry,
    audio_mode=False,
    preferred_audio_lang=None,
    force_original=None,
    audio_track_id=None,
):
    formats = entry.get("formats", [])
    if audio_mode:
        preferred_audio = int(config_get("defaultaudioquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats,
            preferred_audio,
            is_video=False,
            preferred_audio_lang=preferred_audio_lang,
            force_original=force_original,
            audio_track_id=audio_track_id,
        )
    else:
        preferred_video = int(config_get("defaultvideoquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats,
            preferred_video,
            is_video=True,
            preferred_audio_lang=preferred_audio_lang,
            force_original=force_original,
            audio_track_id=audio_track_id,
        )

    if not fmt:
        fmt = entry

    title = entry.get("title")
    url_to_play = fmt.get("url")
    if not url_to_play:
        return None

    headers = {}
    headers.update(entry.get("http_headers", {}) or {})
    headers.update(fmt.get("http_headers", {}) or {})
    headers.setdefault("User-Agent", "libmpv")

    audio_url = audio_fmt.get("url") if audio_fmt else None
    track_info = (
        (audio_fmt.get("_chosen_track") if isinstance(audio_fmt, dict) else None)
        or (fmt.get("_chosen_track") if isinstance(fmt, dict) else None)
        or {}
    )
    return Stream(
        title,
        url_to_play,
        headers,
        audio_url,
        quality=quality,
        webpage_url=entry.get("webpage_url") or entry.get("original_url") or "",
        channel_name=entry.get("channel") or entry.get("uploader") or "",
        channel_url=entry.get("channel_url") or entry.get("uploader_url") or "",
        view_count=entry.get("view_count"),
        upload_date=entry.get("upload_date") or entry.get("timestamp") or "",
        audio_track_id=track_info.get("id"),
        audio_track_lang=track_info.get("lang"),
        audio_track_label=track_info.get("label"),
    )


def _begin_stream_extraction(cache_key):
    with _stream_inflight_lock:
        event = _stream_inflight.get(cache_key)
        if event is not None:
            return event, False
        event = threading.Event()
        _stream_inflight[cache_key] = event
        return event, True


def _finish_stream_extraction(cache_key, event):
    with _stream_inflight_lock:
        if _stream_inflight.get(cache_key) is event:
            del _stream_inflight[cache_key]
        event.set()


def get_playable_stream(url, audio_mode=False):
    if "youtube.com" not in url and "youtu.be" not in url:
        url_full = f"https://www.youtube.com/watch?v={url}"
    else:
        url_full = url

    cache_key = f"{url_full}_{'audio' if audio_mode else 'video'}"
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return _attach_sponsorblock_segments(cached, url_full)

    cached_info = _info_cache.get(url_full, ttl=1200)
    if cached_info:
        stream = _stream_from_info(cached_info, audio_mode=audio_mode)
        if stream:
            _stream_cache.set(cache_key, stream)
            return _attach_sponsorblock_segments(stream, url_full)

    # Handle Mix/Playlist URLs via deno service
    playlist_id = None
    if "list=" in url_full:
        playlist_id_match = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url_full)
        if playlist_id_match:
            playlist_id = playlist_id_match.group(1)

    # Catch-all for Mix/RD patterns
    if not playlist_id:
        mix_id_match = re.search(r"(RD[a-zA-Z0-9_-]+)", url_full)
        if mix_id_match:
            playlist_id = mix_id_match.group(1)

    logger.info(
        f"DEBUG: Checking for playlist_id. URL: {url_full}. Detected ID: {playlist_id}"
    )

    if playlist_id:
        cookies_path = config_get("cookiespath")
        result = deno_service.send_command(
            "get_playlist",
            {
                "playlistId": playlist_id,
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
            },
        )
        if isinstance(result, dict) and "videos" in result and result["videos"]:
            # Pick the first video to play
            first_video = result["videos"][0]
            url_full = first_video["url"]
            # We don't cache playlist extraction, but we can cache the stream of the first video
            return get_playable_stream(url_full, audio_mode=audio_mode)

    if not YoutubeDL:
        logger.error("yt-dlp is not installed")
        if audio_mode:
            return _attach_sponsorblock_segments(get_audio_stream(url_full), url_full)
        return _attach_sponsorblock_segments(get_video_stream(url_full), url_full)

    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    url = url_full
    event, owner = _begin_stream_extraction(url_full)
    if not owner:
        event.wait(timeout=30)
        cached = _stream_cache.get(cache_key, ttl=1200)
        if cached:
            return _attach_sponsorblock_segments(cached, url_full)
        cached_info = _info_cache.get(url_full, ttl=1200)
        if cached_info:
            stream = _stream_from_info(cached_info, audio_mode=audio_mode)
            if stream:
                _stream_cache.set(cache_key, stream)
                return _attach_sponsorblock_segments(stream, url_full)
        return None

    logger.info(f"Extracting URL: {url}")
    cookies_path = config_get("cookiespath")

    def _extract_task(client):
        try:
            with get_ydl_instance(client, cookies_path) as ydl:
                try:
                    entry = ydl.extract_info(url, download=False)
                except Exception as e:
                    if "format" in str(e).lower():
                        retry_opts = PLAYER_OPTS.copy()
                        retry_opts.update(
                            {
                                "extractor_args": {
                                    "youtube": {
                                        "player_client": ["default"],
                                        "js_variant": "main",
                                    }
                                },
                                "js_runtimes": {"deno": {}},
                                "socket_timeout": 5,
                            }
                        )
                        if cookies_path and os.path.exists(cookies_path):
                            retry_opts["cookiefile"] = cookies_path
                        with YoutubeDL(retry_opts) as ydl_retry:
                            entry = ydl_retry.extract_info(url, download=False)
                    else:
                        raise

            _info_cache.set(url, entry)
            return _stream_from_info(entry, audio_mode=audio_mode)
        except Exception:
            logger.exception("Extraction failed for client %s", client)
            return None

    try:
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))
        clients = get_configured_player_clients(has_cookies=has_cookies)
        result = _extract_task(clients)
        if not result and clients != ["default"]:
            logger.warning(
                "Extraction failed with client %s, retrying with 'default' client",
                clients,
            )
            result = _extract_task(["default"])

        if result:
            _stream_cache.set(cache_key, result)
            return _attach_sponsorblock_segments(result, url_full)

        logger.error(f"Extraction failed for {url}")
        return None
    finally:
        _finish_stream_extraction(url_full, event)


def get_media_info(url):
    cached = _info_cache.get(url, ttl=3600)
    if cached:
        return cached

    if not YoutubeDL:
        return None

    cookies_path = config_get("cookiespath")
    has_cookies = bool(cookies_path and os.path.exists(cookies_path))

    def _extract_info_task(client):
        try:
            with get_ydl_instance(client, cookies_path) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            logger.exception("get_media_info extraction failed for client %s", client)
            return None

    clients = get_configured_player_clients(has_cookies=has_cookies)
    info = _extract_info_task(clients)
    if not info and clients != ["default"]:
        logger.warning(
            "get_media_info failed for client %s; retrying with 'default' client",
            clients,
        )
        info = _extract_info_task(["default"])

    if info:
        _info_cache.set(url, info)
        return info

    logger.error(f"get_media_info failed for {url}")
    return None


def get_audio_stream(url):
    cache_key = f"{url}_audio"
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached
    info = get_media_info(url)
    if info is None:
        return None
    stream = _stream_from_info(info, audio_mode=True)
    if stream:
        _stream_cache.set(cache_key, stream)
    return stream


def get_video_stream(url):
    cache_key = f"{url}_video"
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached
    info = get_media_info(url)
    if info is None:
        return None
    stream = _stream_from_info(info, audio_mode=False)
    if stream:
        _stream_cache.set(cache_key, stream)
    return stream


def get_available_qualities(url, audio_mode=False):
    info = get_media_info(url)
    if info is None:
        return []
    formats = info.get("formats", [])
    if not audio_mode:
        available = [
            f.get("height")
            for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]
    else:
        available = [
            f.get("abr")
            for f in formats
            if f.get("acodec") != "none"
            and f.get("vcodec") == "none"
            and f.get("abr") is not None
        ]
    return sorted(set(available))


def get_available_subtitles(url):
    info = get_media_info(url)
    return _normalize_subtitle_tracks(info)


def get_subtitle_cues(url, language_code):
    info = get_media_info(url)
    tracks = _normalize_subtitle_tracks(info)
    track = next(
        (track for track in tracks if track["code"] == language_code),
        None,
    )
    if not track:
        return []

    track_url = track.get("url")
    if track_url:
        cached = _subtitle_cues_cache.get(track_url)
        if cached is not None:
            return cached

    try:
        response = requests.get(track["url"], timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(
            "Failed to download subtitles for %s language=%s: %s",
            url,
            language_code,
            e,
        )
        return []

    cues = _parse_subtitle_cues(response.text, track.get("ext"))
    if cues and track_url:
        _subtitle_cues_cache.set(track_url, cues)
    return cues


def get_specific_quality_stream(url, height, audio_mode=False, audio_track_id=None):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    stream, audio_stream, quality = pick_best_format(
        formats,
        0,
        is_video=not audio_mode,
        target_height=height if not audio_mode else None,
        audio_track_id=audio_track_id,
    )
    if audio_mode and isinstance(height, int):
        for f in formats:
            if (
                f.get("acodec") != "none"
                and f.get("vcodec") == "none"
                and f.get("abr") == height
            ):
                stream = f
                quality = f.get("abr")
                break

    if stream:
        audio_url = audio_stream.get("url") if audio_stream else None
        track_info = (
            (
                audio_stream.get("_chosen_track")
                if isinstance(audio_stream, dict)
                else None
            )
            or (stream.get("_chosen_track") if isinstance(stream, dict) else None)
            or {}
        )
        headers = {}
        headers.update(info.get("http_headers", {}) or {})
        headers.update(stream.get("http_headers", {}) or {})
        return Stream(
            title,
            stream["url"],
            headers=headers,
            audio_url=audio_url,
            quality=quality,
            webpage_url=info.get("webpage_url") or info.get("original_url") or "",
            channel_name=info.get("channel") or info.get("uploader") or "",
            channel_url=info.get("channel_url") or info.get("uploader_url") or "",
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date") or info.get("timestamp") or "",
            audio_track_id=track_info.get("id"),
            audio_track_lang=track_info.get("lang"),
            audio_track_label=track_info.get("label"),
        )
    return None


def get_home_feed(continuation=None, parent=None):
    feature_name = _("عرض الخلاصة الرئيسية")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {
            "videos": [],
            "continuation": None,
            "error": _("لم يتم تثبيت Deno."),
        }

    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {
            "videos": [],
            "continuation": None,
            "error": _("لم يتم ضبط ملف الكوكيز."),
        }

    cookies_path = config_get("cookiespath")
    result = deno_service.send_command(
        "get_home_feed",
        {
            "cookiesPath": cookies_path,
            "continuationToken": continuation,
            "location": get_windows_region(),
        },
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(f"Deno service error: {result['error']}")
        return {"videos": [], "continuation": None, "error": result["error"]}

    if result is None:
        return {"videos": [], "continuation": None}

    return result


def get_watch_history(continuation=None, parent=None):
    feature_name = _("سجل المشاهدة أونلاين")
    if not ensure_deno_installed(
        parent=parent, feature_name=feature_name
    ) or not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        err_msg = _(
            "عذراً، يتطلب عرض سجل يوتيوب أونلاين وجود Deno وملف كوكيز. يتم عرض السجل المحلي حالياً."
        )
        return _local_watch_history_response(continuation, error=err_msg)

    cookies_path = config_get("cookiespath")
    result = deno_service.send_command(
        "get_watch_history",
        {
            "cookiesPath": cookies_path,
            "continuationToken": continuation,
            "location": get_windows_region(),
        },
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(f"Deno service error: {result['error']}")
        return _local_watch_history_response(continuation)

    if result is None:
        return _local_watch_history_response(continuation)

    return result


def _local_watch_history_response(continuation=None, page_size=50, error=None):
    try:
        offset = int(continuation or 0)
    except TypeError, ValueError:
        offset = 0
    offset = max(0, offset)

    rows = WatchHistory.get_page(page_size + 1, offset) or []
    videos = rows[:page_size]
    next_offset = offset + page_size if len(rows) > page_size else None
    response = {
        "videos": videos,
        "continuation": str(next_offset) if next_offset is not None else None,
        "source": "local",
    }
    if error:
        response["error"] = error
    return response


def update_watch_history(
    url,
    watched_seconds=0,
    title="",
    channel_name="",
    channel_url="",
    is_live=False,
):
    match = youtube_regexp(url)
    if not match:
        return
    video_id = match.group(5)

    WatchHistory.add_or_update(
        {
            "title": title or video_id,
            "url": url,
            "channel_name": channel_name,
            "channel_url": channel_url,
            "is_live": is_live,
            "watched_seconds": watched_seconds,
        }
    )

    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return

    try:
        result = deno_service.send_command(
            "update_watch_history",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "watchedSeconds": str(watched_seconds),
                "location": get_windows_region(),
            },
        )
        if isinstance(result, dict) and result.get("success"):
            return
    except Exception as e:
        logger.debug("Deno service update_watch_history failed, falling back: %s", e)

    try:
        env = os.environ.copy()
        env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
        bundled_path = paths.get_bundled_data_path()
        script_path = os.path.join(bundled_path, "update_history.js")
        config_path = os.path.join(bundled_path, "deno.json")

        command = [
            paths.get_deno_path(),
            "run",
            "--allow-read",
            "--allow-write",
            "--allow-net",
            "--allow-env",
            "--config",
            config_path,
            script_path,
            video_id,
            cookies_path,
            str(watched_seconds),
        ]

        subprocess.run(
            command,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            cwd=paths.main_path,
            env=env,
            capture_output=True,
            check=False,
        )
    except Exception as e:
        logger.error(f"Error updating watch history: {e}")


def like_video(url, action="like", parent=None):
    """
    Performs a like, dislike, or remove_like interaction on a video.
    Actions: 'like', 'dislike', 'remove_like'
    Returns dict: {"success": bool, "error": str or None}
    """
    feature_name = _("إبداء الإعجاب بالمرئيات")

    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("لم يتم تثبيت أداة Deno المطلوبة للإعجاب بالمرئيات."),
        }

    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("لم يتم ضبط ملف الكوكيز الخاص بيوتيوب."),
        }

    match = youtube_regexp(url)
    if not match:
        return {
            "success": False,
            "error": _("رابط الفيديو غير صالح."),
        }
    video_id = match.group(5)

    try:
        result = deno_service.send_command(
            "like_video",
            {
                "cookiesPath": config_get("cookiespath"),
                "videoId": video_id,
                "action": action,
            },
        )
        if isinstance(result, dict) and result.get("success"):
            return {"success": True, "error": None}

        err_msg = result.get("error") if isinstance(result, dict) else None
        return {
            "success": False,
            "error": _("تعذر تحديث تقييم المرئي: {}").format(
                err_msg or _("خطأ غير معروف")
            ),
        }
    except Exception as e:
        logger.error(f"Failed to perform like interaction: {e}")
        return {
            "success": False,
            "error": _("فشل الاتصال أثناء تحديث التقييم: {}").format(e),
        }


def get_video_likes(url):
    """
    Fetches the like count for a video.
    """
    return get_video_like_info(url)["likes"]


def get_video_like_info(url):
    """
    Fetches the like count and current like/dislike status for a video.
    """
    cookies_path = config_get("cookiespath")
    match = youtube_regexp(url)
    if not match:
        logger.error(f"Failed to match URL: {url}")
        return _normalize_like_info(None)
    video_id = match.group(5)
    logger.info(f"Fetching likes for video_id: {video_id} with cookies: {cookies_path}")

    try:
        result = deno_service.send_command(
            "get_video_likes",
            {"cookiesPath": cookies_path, "videoId": video_id},
        )
        logger.info(f"Deno service result for likes: {result}")
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Deno service returned like info error: {result['error']}")
        info = _normalize_like_info(result)
        if info["likes"] is None:
            fallback_info = _get_video_like_info_with_yt_dlp(url, cookies_path)
            if fallback_info["likes"] is not None:
                info["likes"] = fallback_info["likes"]
        return info
    except Exception as e:
        logger.error(f"Failed to perform like interaction: {e}")
        return _get_video_like_info_with_yt_dlp(url, cookies_path)


def _get_video_like_info_with_yt_dlp(url, cookies_path=None):
    info = _normalize_like_info(None)
    if not YoutubeDL:
        return info

    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
    opts["skip_download"] = True
    opts["extract_flat"] = False
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path

    try:
        with YoutubeDL(opts) as ydl:
            video_info = ydl.extract_info(url, download=False)
        info["likes"] = _coerce_count(
            video_info.get("like_count") if video_info else None
        )
    except Exception as e:
        logger.error(f"Failed to fetch like count with yt-dlp fallback: {e}")
    return info


def _get_video_chapters_with_yt_dlp(url, cookies_path=None):
    if not YoutubeDL:
        return []

    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
    opts["skip_download"] = True
    opts["extract_flat"] = False
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return _normalize_video_chapters(info.get("chapters") if info else [])
    except Exception as e:
        logger.error(f"Failed to fetch chapters with yt-dlp fallback: {e}")
        return []


def get_video_chapters(url):
    """
    Fetches the chapters for a video.
    Returns a list of dictionaries with 'title' and 'time_ms'.
    """
    cookies_path = config_get("cookiespath")
    match = youtube_regexp(url)
    if not match:
        logger.error(f"Failed to match URL for chapters: {url}")
        return []
    video_id = match.group(5)

    try:
        result = deno_service.send_command(
            "get_video_chapters",
            {"cookiesPath": cookies_path, "videoId": video_id},
        )
        chapters = _normalize_video_chapters(result)
        if chapters:
            return chapters
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Deno service returned chapters error: {result['error']}")
        return _get_video_chapters_with_yt_dlp(url, cookies_path)
    except Exception as e:
        logger.error(f"Failed to fetch chapters: {e}")
        return _get_video_chapters_with_yt_dlp(url, cookies_path)


def _normalize_comment_item(comment):
    if not isinstance(comment, dict):
        return None

    return {
        "id": str(comment.get("id") or ""),
        "parent_id": str(comment.get("parent_id") or comment.get("parent") or ""),
        "author": str(comment.get("author") or _("غير معروف")),
        "content": str(comment.get("content") or ""),
        "published_time": str(comment.get("published_time") or ""),
        "likes": _coerce_count(comment.get("likes")) or 0,
        "replies": _coerce_count(comment.get("replies")) or 0,
        "has_replies": bool(comment.get("has_replies") or comment.get("reply_token")),
        "reply_token": comment.get("reply_token"),
        "is_liked": bool(comment.get("is_liked")),
        "is_disliked": bool(comment.get("is_disliked")),
    }


def _normalize_comments_response(result):
    if not isinstance(result, dict) or "error" in result:
        return {
            "comments": [],
            "continuation": None,
            "is_disabled": bool(result.get("is_disabled"))
            if isinstance(result, dict)
            else False,
        }

    comments = []
    for comment in result.get("comments", []):
        normalized = _normalize_comment_item(comment)
        if normalized is not None:
            comments.append(normalized)

    return {
        "comments": comments,
        "continuation": result.get("continuation"),
        "is_disabled": bool(result.get("is_disabled")),
    }


def _normalize_yt_dlp_comment(comment):
    text = comment.get("text") or comment.get("content") or ""
    return _normalize_comment_item(
        {
            "id": comment.get("id"),
            "parent_id": comment.get("parent"),
            "author": comment.get("author"),
            "content": text,
            "published_time": comment.get("_time_text") or comment.get("time_text"),
            "likes": comment.get("like_count"),
            "replies": 0,
            "has_replies": False,
            "reply_token": None,
        }
    )


def _get_comments_with_yt_dlp(url, parent_id=None, max_comments=200):
    if not YoutubeDL:
        return {"comments": [], "continuation": None}

    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
    opts["skip_download"] = True
    opts["getcomments"] = True
    opts["extract_flat"] = False
    opts["extractor_args"] = {"youtube": {"max_comments": [str(max_comments)]}}

    cookies_path = config_get("cookiespath")
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Failed to fetch comments with yt-dlp fallback: {e}")
        return {"comments": [], "continuation": None}

    comments = []
    for comment in info.get("comments", []) if info else []:
        parent = comment.get("parent")
        if parent_id:
            if parent != parent_id:
                continue
        elif parent not in (None, "", "root"):
            continue
        normalized = _normalize_yt_dlp_comment(comment)
        if normalized is not None:
            comments.append(normalized)

    return {"comments": comments, "continuation": None}


def get_video_comments(url, continuation=None, sort_by="TOP_COMMENTS"):
    """
    Fetches video comments.
    """
    cookies_path = config_get("cookiespath")
    match = youtube_regexp(url)
    if not match:
        logger.error(f"Failed to match URL for comments: {url}")
        return {"comments": [], "continuation": None}
    video_id = match.group(5)

    try:
        result = deno_service.send_command(
            "get_video_comments",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "continuationToken": continuation,
                "sortBy": sort_by,
            },
        )
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Deno service returned comments error: {result['error']}")
        data = _normalize_comments_response(result)
        if not data["comments"] and not continuation:
            return _get_comments_with_yt_dlp(url)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch comments: {e}")
        if not continuation:
            return _get_comments_with_yt_dlp(url)
        return {"comments": [], "continuation": None}


def get_comment_replies(reply_token, continuation=None, video_url=None, parent_id=None):
    """
    Fetches replies for a comment returned by get_video_comments.
    """
    if not reply_token and not continuation:
        return {"comments": [], "continuation": None}

    try:
        result = deno_service.send_command(
            "get_comment_replies",
            {"replyToken": reply_token, "continuationToken": continuation},
        )
        if isinstance(result, dict) and "error" in result:
            logger.warning(
                f"Deno service returned comment replies error: {result['error']}"
            )
        data = _normalize_comments_response(result)
        if not data["comments"] and video_url and parent_id and not continuation:
            return _get_comments_with_yt_dlp(video_url, parent_id=parent_id)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch comment replies: {e}")
        if video_url and parent_id and not continuation:
            return _get_comments_with_yt_dlp(video_url, parent_id=parent_id)
        return {"comments": [], "continuation": None}


def _post_comment_error_message(error=None):
    text = str(error or "").lower()
    if "comment text" in text:
        return _("يرجى كتابة تعليق قبل النشر")
    if "cookies path" in text or "cookie" in text:
        return _("تحتاج إلى ضبط ملف كوكيز صالح قبل نشر التعليقات")
    if "not logged" in text or "signed in" in text:
        return _("ملف الكوكيز لا يحتوي على جلسة يوتيوب مسجلة الدخول")
    return _("تعذر نشر التعليق")


def post_video_comment(url, text, parent=None):
    """
    Posts a top-level comment on a YouTube video using configured cookies.
    """
    feature_name = _("نشر التعليقات")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("لم يتم تثبيت أداة Deno المطلوبة لنشر التعليقات."),
        }
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("تحتاج إلى ضبط ملف كوكيز صالح لنشر التعليقات."),
        }

    comment_text = str(text or "").strip()
    if not comment_text:
        return {"success": False, "error": _post_comment_error_message("comment text")}

    cookies_path = config_get("cookiespath")

    match = youtube_regexp(url)
    if not match:
        logger.error(f"Failed to match URL for comment posting: {url}")
        return {
            "success": False,
            "error": _("رابط الفيديو غير صالح"),
        }
    video_id = match.group(5)

    try:
        result = deno_service.send_command(
            "post_video_comment",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "text": comment_text,
            },
        )
        if isinstance(result, dict) and result.get("success"):
            return {"success": True, "error": None}

        error = result.get("error") if isinstance(result, dict) else None
        if error:
            logger.warning(f"Deno service returned comment post error: {error}")
        return {"success": False, "error": _post_comment_error_message(error)}
    except Exception as e:
        logger.error(f"Failed to post video comment: {e}")
        return {"success": False, "error": _post_comment_error_message(e)}


def like_comment(url, comment_id, action="like", parent=None):
    """
    Likes, dislikes, or removes vote on a comment.
    action can be 'like', 'dislike', or 'remove_like'.
    """
    feature_name = _("التفاعل مع التعليقات")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("لم يتم تثبيت أداة Deno المطلوبة للتفاعل مع التعليقات."),
        }
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("تحتاج إلى ضبط ملف كوكيز صالح لاستخدام هذه الميزة"),
        }

    if not comment_id:
        return {
            "success": False,
            "error": _("معرف التعليق غير موجود"),
        }

    cookies_path = config_get("cookiespath")

    match = youtube_regexp(url) if url else None
    video_id = match.group(5) if match else None

    try:
        result = deno_service.send_command(
            "like_comment",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "commentId": comment_id,
                "action": action,
            },
        )
        return result
    except Exception as e:
        logger.error(f"Failed to perform comment action: {e}")
        return {"success": False, "error": str(e)}


def reply_to_comment(url, comment_id, text, parent=None):
    """
    Posts a reply to a specific comment.
    """
    feature_name = _("الرد على التعليقات")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("لم يتم تثبيت أداة Deno المطلوبة للرد على التعليقات."),
        }
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {
            "success": False,
            "error": _("تحتاج إلى ضبط ملف كوكيز صالح للرد على التعليقات."),
        }

    if not comment_id:
        return {
            "success": False,
            "error": _("معرف التعليق غير موجود"),
        }

    reply_text = str(text or "").strip()
    if not reply_text:
        return {
            "success": False,
            "error": _("يرجى كتابة رد قبل النشر"),
        }

    cookies_path = config_get("cookiespath")

    match = youtube_regexp(url) if url else None
    video_id = match.group(5) if match else None

    try:
        result = deno_service.send_command(
            "reply_to_comment",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "commentId": comment_id,
                "text": reply_text,
            },
        )
        return result
    except Exception as e:
        logger.error(f"Failed to reply to comment: {e}")
        return {"success": False, "error": str(e)}


def time_formatting(total_seconds):
    if total_seconds is None:
        return ""
    try:
        total_seconds = int(total_seconds)
    except ValueError, TypeError:
        return ""

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours > 0:
        if hours == 1:
            parts.append(_("ساعة واحدة"))
        elif hours == 2:
            parts.append(_("ساعتان"))
        elif 3 <= hours <= 10:
            parts.append(_("{} ساعات").format(hours))
        else:
            parts.append(_("{} ساعة").format(hours))

    if minutes > 0:
        if minutes == 1:
            parts.append(_("دقيقة واحدة"))
        elif minutes == 2:
            parts.append(_("دقيقتان"))
        elif 3 <= minutes <= 10:
            parts.append(_("{} دقائق").format(minutes))
        else:
            parts.append(_("{} دقيقة").format(minutes))

    if seconds > 0 or (not parts and total_seconds == 0):
        if seconds == 1:
            parts.append(_("ثانية واحدة"))
        elif seconds == 2:
            parts.append(_("ثانيتين"))
        elif 3 <= seconds <= 10:
            parts.append(_("{} ثواني").format(seconds))
        else:
            parts.append(_("{} ثانية").format(seconds))

    if not parts:
        return _("0 ثانية")

    return _(" و").join(parts)


def format_duration(duration):
    if duration is None:
        return _("مباشر")
    if isinstance(duration, str):
        seconds = time_to_seconds(duration)
    else:
        seconds = duration
    if seconds is None:
        return _("غير معروف")
    return _("المدة: {}").format(time_formatting(seconds))


def time_to_seconds(time_str):
    if not isinstance(time_str, str):
        return None
    parts = time_str.split(":")
    total_seconds = 0
    try:
        if len(parts) == 3:  # HH:MM:SS
            total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:  # MM:SS
            total_seconds = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:  # SS
            total_seconds = int(parts[0])
        else:
            return None
    except ValueError:
        return None
    return total_seconds


def sanitize_filename(filename):
    if not filename:
        return "unnamed"
    return re.sub(r'[<>:"/\\|?*]', "_", filename).strip()


def _app_update_platform_target():
    if sys.platform == "win32":
        return "windows", "x86_64"
    if sys.platform.startswith("linux"):
        machine = platform.machine().lower()
        arch = {
            "amd64": "x86_64",
            "x86_64": "x86_64",
            "arm64": "aarch64",
            "aarch64": "aarch64",
        }.get(machine)
        if arch:
            return "linux", arch
    return None, None


RELEASES_PAGE_URL = (
    "https://github.com/makhlwf/accessible_youtube_downloader_pro/releases"
)


def _detect_linux_distro_family(os_release_data=None):
    override = os.environ.get("HEXPLAYER_DISTRO_OVERRIDE", "").strip().lower()
    if override:
        if override in ("fedora", "rhel", "centos", "rocky", "almalinux", "rpm"):
            return "fedora"
        if override in ("debian", "ubuntu", "linuxmint", "pop", "deb"):
            return "debian"
        return override

    data = os_release_data
    if data is None:
        os_file = os.environ.get("OS_RELEASE_FILE")
        if os_file:
            if os.path.isfile(os_file):
                data = _parse_os_release_file(os_file)
            else:
                data = {}
        else:
            try:
                if hasattr(platform, "freedesktop_os_release"):
                    data = platform.freedesktop_os_release()
            except OSError:
                data = {}
            if not data:
                for candidate in ("/etc/os-release", "/usr/lib/os-release"):
                    if os.path.isfile(candidate):
                        data = _parse_os_release_file(candidate)
                        break

    if not data or not isinstance(data, dict):
        return "unknown"

    distro_id = str(data.get("ID", "")).lower().strip("\"' ")
    distro_like = str(data.get("ID_LIKE", "")).lower().strip("\"' ")
    tokens = {distro_id} | set(distro_like.split())

    fedora_tokens = {
        "fedora",
        "rhel",
        "centos",
        "rocky",
        "almalinux",
        "ol",
        "scientific",
    }
    debian_tokens = {
        "debian",
        "ubuntu",
        "linuxmint",
        "pop",
        "elementary",
        "zorin",
        "kali",
        "raspbian",
    }

    if distro_id in fedora_tokens:
        return "fedora"
    if distro_id in debian_tokens:
        return "debian"
    if tokens & fedora_tokens:
        return "fedora"
    if tokens & debian_tokens:
        return "debian"
    return "unknown"


def _parse_os_release_file(path):
    data = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                data[key] = val
    except OSError:
        pass
    return data


def _extract_candidate_urls(entry):
    urls = []
    if isinstance(entry, str):
        urls.append(entry)
    elif isinstance(entry, dict):
        for k in ("url", "browser_download_url"):
            v = entry.get(k)
            if isinstance(v, str):
                urls.append(v)
        for k, v in entry.items():
            if k not in ("url", "browser_download_url"):
                urls.extend(_extract_candidate_urls(v))
    elif isinstance(entry, (list, tuple)):
        for item in entry:
            urls.extend(_extract_candidate_urls(item))
    return urls


def _linux_release_asset_url(url, arch, distro=None):
    if not isinstance(url, str):
        return ""
    if not url.startswith("https://github.com/"):
        return ""

    rpm_suffixes = [
        f"-1.{arch}.rpm",
        f"-linux-{arch}.rpm",
        f"-{arch}.rpm",
        f".{arch}.rpm",
    ]
    deb_suffixes = [
        f"-linux-{arch}.deb",
        f"-{arch}.deb",
        f"_{arch}.deb",
        f".{arch}.deb",
    ]
    if arch in ("x86_64", "amd64"):
        deb_suffixes.extend(
            ["-linux-amd64.deb", "-amd64.deb", "_amd64.deb", ".amd64.deb"]
        )
    elif arch == "aarch64":
        deb_suffixes.extend(
            ["-linux-arm64.deb", "-arm64.deb", "_arm64.deb", ".arm64.deb"]
        )

    tar_suffixes = [f"-linux-{arch}.tar.gz", f"-{arch}.tar.gz"]

    if distro == "fedora":
        suffixes = rpm_suffixes + tar_suffixes
    elif distro == "debian":
        suffixes = deb_suffixes + tar_suffixes
    else:
        suffixes = rpm_suffixes + deb_suffixes + tar_suffixes

    for suffix in suffixes:
        if url.endswith(suffix):
            return url
    return ""


def _select_app_update(info):
    platform_key, arch = _app_update_platform_target()
    if not platform_key:
        return RELEASES_PAGE_URL, False
    if platform_key == "windows":
        url = info.get("url") if isinstance(info, dict) else None
        return (url if isinstance(url, str) else ""), bool(url)

    distro = _detect_linux_distro_family()
    platforms = info.get("platforms") if isinstance(info, dict) else None

    candidates = []
    if isinstance(platforms, dict):
        if distro and distro in platforms:
            candidates.extend(_extract_candidate_urls(platforms[distro]))
        if distro == "fedora" and "rpm" in platforms:
            candidates.extend(_extract_candidate_urls(platforms["rpm"]))
        elif distro == "debian":
            for deb_key in ("ubuntu", "deb"):
                if deb_key in platforms:
                    candidates.extend(_extract_candidate_urls(platforms[deb_key]))

        if platform_key in platforms:
            candidates.extend(_extract_candidate_urls(platforms[platform_key]))

        for k, v in platforms.items():
            if k not in (distro, platform_key, "rpm", "deb", "ubuntu"):
                candidates.extend(_extract_candidate_urls(v))

    if isinstance(info, dict) and "assets" in info:
        candidates.extend(_extract_candidate_urls(info["assets"]))

    valid_urls = []
    seen = set()
    for cand in candidates:
        matched = _linux_release_asset_url(cand, arch, distro=distro)
        if matched and matched not in seen:
            seen.add(matched)
            valid_urls.append(matched)

    if not valid_urls:
        return RELEASES_PAGE_URL, False

    def _rank_url(u):
        if distro == "fedora":
            if u.endswith(".rpm"):
                return 0
            if u.endswith(".tar.gz"):
                return 1
            return 2
        elif distro == "debian":
            if u.endswith(".deb"):
                return 0
            if u.endswith(".tar.gz"):
                return 1
            return 2
        else:
            if u.endswith((".rpm", ".deb")):
                return 0
            return 1

    valid_urls.sort(key=_rank_url)
    return valid_urls[0], True


def check_for_updates(quiet=False):
    new_url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update.json"
    old_url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update_info.json"
    try:
        r = requests.get(new_url, timeout=10)
        if r.status_code == 200:
            info = r.json()
        else:
            r = requests.get(old_url, timeout=10)
            if r.status_code == 200:
                info = r.json()
            else:
                if not quiet:
                    show_error(
                        _(
                            "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                        ),
                    )
                return
        if application.version != info["version"]:
            url, in_app_download = _select_app_update(info)

            def show_update_dialog():
                from gui.update_check_dialog import UpdateCheckDialog

                new_version = info["version"]
                whats_new = info.get("whats_new", _("لا توجد معلومات حول هذا التحديث"))
                dlg = UpdateCheckDialog(
                    wx.GetApp().GetTopWindow(),
                    new_version,
                    whats_new,
                    url=url,
                    can_download=in_app_download,
                )
                if dlg.ShowModal() == wx.ID_OK and in_app_download:
                    from gui.update_dialog import UpdateDialog

                    UpdateDialog(
                        wx.GetApp().GetTopWindow(),
                        url,
                        title=_("جاري تنزيل التحديث"),
                    )
                dlg.Destroy()

            wx.CallAfter(show_update_dialog)
            return
        if not quiet:
            wx.CallAfter(
                wx.MessageBox,
                _("أنت تعمل الآن على آخر تحديث متوفر من التطبيق"),
                _("لا يوجد تحديث"),
                parent=wx.GetApp().GetTopWindow(),
            )
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        if not quiet:
            show_error(
                _(
                    "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                ),
                e,
            )


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


def has_cookies_file():
    cookies_path = config_get("cookiespath")
    return bool(cookies_path and os.path.exists(cookies_path))


def get_shorts_feed(seed_video_id=None, parent=None):
    """
    Fetches YouTube Shorts recommendations feed from Innertube via Deno service.
    Requires a valid cookies file.
    """
    feature_name = _("مشاهدة Shorts")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return []
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return []

    cookies_path = config_get("cookiespath")
    try:
        result = deno_service.send_command(
            "get_shorts_feed",
            {
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
                "seedVideoId": seed_video_id,
            },
        )
        if isinstance(result, dict) and "shorts" in result:
            return result["shorts"]
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to fetch Shorts feed: {result['error']}")
            return []
        return []
    except Exception as e:
        logger.error(f"Error fetching Shorts feed: {e}")
        return []
