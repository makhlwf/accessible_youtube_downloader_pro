import html as html_parser
import json
import logging
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
import zipimport
from concurrent.futures import ThreadPoolExecutor

import requests
import wx

import application
import paths
from database import WatchHistory
from deno_service import deno_service
from language_handler import _
from settings_handler import config_get
from youtube_url_utils import (  # noqa: F401
    extract_launch_youtube_url,
    extract_supported_youtube_url,
    is_supported_youtube_url,
    youtube_regexp,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    def __init__(self, default_ttl=300):
        self.cache = {}
        self.default_ttl = default_ttl
        self.lock = threading.Lock()

    def get(self, url, ttl=None):
        if ttl is None:
            ttl = self.default_ttl
        with self.lock:
            if url in self.cache:
                info, timestamp = self.cache[url]
                if time.time() - timestamp < ttl:
                    return info
                else:
                    del self.cache[url]
        return None

    def set(self, url, info):
        with self.lock:
            self.cache[url] = (info, time.time())


_info_cache = InfoCache()
_stream_cache = InfoCache()
_stream_inflight = {}
_stream_inflight_lock = threading.Lock()
_extraction_executor = ThreadPoolExecutor(max_workers=20)


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

PLAYER_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android_vr"],
            "js_variant": "main",
            "skip": ["dash", "hls"],
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


def get_ydl_instance(client, cookies_path=None):
    """Returns a fresh YoutubeDL instance for thread-safe extraction."""
    if not YoutubeDL:
        return None
    opts = PLAYER_OPTS.copy()
    opts["extractor_args"] = {
        "youtube": {"player_client": client, "js_variant": "main"}
    }
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


def download_yt_dlp():
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
        wx.GetApp().GetTopWindow(),
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
        paths.deno_path,
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
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=env,
        cwd=paths.main_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )


def install_youtubei_version(version, parent=None, success_message=None):
    if not os.path.exists(paths.deno_path):
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


def download_deno():
    from gui.update_dialog import UpdateDialog

    url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
    UpdateDialog(
        wx.GetApp().GetTopWindow(),
        url,
        os.path.join(paths.main_path, "deno.zip"),
        _("جاري تنزيل دينو"),
        is_zip=True,
    )


def get_deno_version():
    if not os.path.exists(paths.deno_path):
        return None
    try:
        result = subprocess.run(
            [paths.deno_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
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
    if not os.path.exists(paths.deno_path):
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
            return os.path.exists(paths.deno_path)
        return False
    return True


def ensure_js_dependencies():
    """Silently ensure JavaScript dependencies are cached by Deno."""
    if not os.path.exists(paths.deno_path):
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
                        paths.deno_path,
                        "cache",
                        "--config",
                        config_path,
                        service_script,
                    ],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


def pick_best_format(formats, preferred_index, is_video=True, target_height=None):
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
            audio_formats = [
                f
                for f in formats
                if f.get("acodec") != "none" and f.get("vcodec") == "none"
            ]
            if audio_formats:
                audio_formats.sort(key=lambda x: x.get("abr") or 0)
                audio_fmt = audio_formats[-1]

        return fmt, audio_fmt, fmt.get("height")
    else:
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
        target_abr = AUDIO_QUALITIES[preferred_index]

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


def _stream_from_info(entry, audio_mode=False):
    formats = entry.get("formats", [])
    if audio_mode:
        preferred_audio = int(config_get("defaultaudioquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats, preferred_audio, is_video=False
        )
    else:
        preferred_video = int(config_get("defaultvideoquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats, preferred_video, is_video=True
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
        return cached

    cached_info = _info_cache.get(url_full, ttl=1200)
    if cached_info:
        stream = _stream_from_info(cached_info, audio_mode=audio_mode)
        if stream:
            _stream_cache.set(cache_key, stream)
            return stream

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
            {"playlistId": playlist_id, "cookiesPath": cookies_path},
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
            return get_audio_stream(url_full)
        return get_video_stream(url_full)

    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    url = url_full
    event, owner = _begin_stream_extraction(url_full)
    if not owner:
        event.wait(timeout=30)
        cached = _stream_cache.get(cache_key, ttl=1200)
        if cached:
            return cached
        cached_info = _info_cache.get(url_full, ttl=1200)
        if cached_info:
            stream = _stream_from_info(cached_info, audio_mode=audio_mode)
            if stream:
                _stream_cache.set(cache_key, stream)
                return stream
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
                        with YoutubeDL(
                            {
                                "quiet": True,
                                "no_warnings": True,
                                "extractor_args": {
                                    "youtube": {
                                        "player_client": client,
                                        "js_variant": "main",
                                    }
                                },
                                "js_runtimes": {"deno": {}},
                                "socket_timeout": 5,
                            }
                        ) as ydl_retry:
                            entry = ydl_retry.extract_info(url, download=False)
                    else:
                        raise

            _info_cache.set(url, entry)
            return _stream_from_info(entry, audio_mode=audio_mode)
        except Exception as e:
            logger.debug(f"Extraction failed for client {client}: {e}")
            return None

    try:
        # Try android (VR) only
        result = _extract_task(["android_vr"])

        if result:
            _stream_cache.set(cache_key, result)
            return result

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

    def _extract_info_task(client):
        try:
            with get_ydl_instance(client, cookies_path) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    # Try android (VR) only
    info = _extract_info_task(["android_vr"])

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

    return _parse_subtitle_cues(response.text, track.get("ext"))


def get_specific_quality_stream(url, height, audio_mode=False):
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
    )
    if audio_mode and isinstance(height, int):
        # For audio, target_height is not really height but we might want to handle it
        # Actually pick_best_format for audio doesn't support target_height yet
        # But we can pass preferred_index
        # Let's just find the closest abr if audio_mode
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
        return Stream(title, stream["url"], audio_url=audio_url, quality=quality)
    return None


def get_home_feed(continuation=None):
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return {"videos": [], "continuation": None}

    result = deno_service.send_command(
        "get_home_feed",
        {"cookiesPath": cookies_path, "continuationToken": continuation},
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(f"Deno service error: {result['error']}")
        return {"videos": [], "continuation": None}

    if result is None:
        return {"videos": [], "continuation": None}

    return result


def get_watch_history(continuation=None):
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return _local_watch_history_response(continuation)

    result = deno_service.send_command(
        "get_watch_history",
        {"cookiesPath": cookies_path, "continuationToken": continuation},
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(f"Deno service error: {result['error']}")
        return _local_watch_history_response(continuation)

    if result is None:
        return _local_watch_history_response(continuation)

    return result


def _local_watch_history_response(continuation=None, page_size=50):
    try:
        offset = int(continuation or 0)
    except TypeError, ValueError:
        offset = 0
    offset = max(0, offset)

    rows = WatchHistory.get_page(page_size + 1, offset) or []
    videos = rows[:page_size]
    next_offset = offset + page_size if len(rows) > page_size else None
    return {
        "videos": videos,
        "continuation": str(next_offset) if next_offset is not None else None,
        "source": "local",
    }


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
        env = os.environ.copy()
        env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
        bundled_path = paths.get_bundled_data_path()
        script_path = os.path.join(bundled_path, "update_history.js")
        config_path = os.path.join(bundled_path, "deno.json")

        command = [
            paths.deno_path,
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
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=paths.main_path,
            env=env,
            capture_output=True,
            check=False,
        )
    except Exception as e:
        logger.error(f"Error updating watch history: {e}")


def like_video(url, action="like"):
    """
    Performs a like, dislike, or remove_like interaction on a video.
    Actions: 'like', 'dislike', 'remove_like'
    """
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return False
    match = youtube_regexp(url)
    if not match:
        return False
    video_id = match.group(5)

    try:
        result = deno_service.send_command(
            "like_video",
            {"cookiesPath": cookies_path, "videoId": video_id, "action": action},
        )
        return result.get("success", False) if isinstance(result, dict) else False
    except Exception as e:
        logger.error(f"Failed to perform like interaction: {e}")
        return False


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
    }


def _normalize_comments_response(result):
    if not isinstance(result, dict) or "error" in result:
        return {"comments": [], "continuation": None}

    comments = []
    for comment in result.get("comments", []):
        normalized = _normalize_comment_item(comment)
        if normalized is not None:
            comments.append(normalized)

    return {"comments": comments, "continuation": result.get("continuation")}


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


def post_video_comment(url, text):
    """
    Posts a top-level comment on a YouTube video using configured cookies.
    """
    comment_text = str(text or "").strip()
    if not comment_text:
        return {"success": False, "error": _post_comment_error_message("comment text")}

    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return {"success": False, "error": _post_comment_error_message("cookies path")}

    match = youtube_regexp(url)
    if not match:
        logger.error(f"Failed to match URL for comment posting: {url}")
        return {"success": False, "error": _("رابط الفيديو غير صالح")}
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

            def show_update_dialog():
                from gui.update_check_dialog import UpdateCheckDialog

                new_version = info["version"]
                whats_new = info.get("whats_new", _("لا توجد معلومات حول هذا التحديث"))
                url = info["url"]
                dlg = UpdateCheckDialog(
                    wx.GetApp().GetTopWindow(), new_version, whats_new
                )
                if dlg.ShowModal() == wx.ID_OK:
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


def set_startup(enable: bool):
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
