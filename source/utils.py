import sys
import re
import requests
import wx
import application
import paths
import subprocess
import os
import logging
import time
import threading
import socket
import zipfile
import zipimport
from concurrent.futures import ThreadPoolExecutor
from settings_handler import config_get
from language_handler import _
from deno_service import deno_service
from youtube_url_utils import (
    extract_launch_youtube_url as extract_launch_youtube_url,
    extract_supported_youtube_url as extract_supported_youtube_url,
    is_supported_youtube_url as is_supported_youtube_url,
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
        return int(value) if value == value else None

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
    return int(round(number * multiplier))


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
            except (TypeError, ValueError):
                continue

    for key in ("start_time", "startTime"):
        if key in chapter and chapter[key] is not None:
            try:
                return max(0, int(float(chapter[key]) * 1000))
            except (TypeError, ValueError):
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

    bundled_path = paths.get_bundled_data_path()
    service_script = os.path.join(bundled_path, "service.js")
    config_path = os.path.join(bundled_path, "deno.json")

    # If not in bundled path, try main path
    if not os.path.exists(service_script):
        service_script = os.path.join(paths.main_path, "service.js")
        config_path = os.path.join(paths.main_path, "deno.json")

    if not os.path.exists(service_script) or not os.path.exists(config_path):
        return

    def _cache_task():
        try:
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
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
                cwd=paths.main_path,
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
            except (ValueError, StopIteration):
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
                        raise e

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
    return sorted(list(set(available)))


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
    if audio_mode:
        # For audio, target_height is not really height but we might want to handle it
        # Actually pick_best_format for audio doesn't support target_height yet
        # But we can pass preferred_index
        # Let's just find the closest abr if audio_mode
        if isinstance(height, int):
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
        return {"videos": [], "continuation": None}

    result = deno_service.send_command(
        "get_watch_history",
        {"cookiesPath": cookies_path, "continuationToken": continuation},
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(f"Deno service error: {result['error']}")
        return {"videos": [], "continuation": None}

    if result is None:
        return {"videos": [], "continuation": None}

    return result


def update_watch_history(url, watched_seconds=0):
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return

    match = youtube_regexp(url)
    if not match:
        return
    video_id = match.group(5)

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


def time_formatting(total_seconds):
    if total_seconds is None:
        return ""
    try:
        total_seconds = int(total_seconds)
    except (ValueError, TypeError):
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
                        _("جاري تنزيل التحديث"),
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
        message = f"{message}\n\nDebug Info:\n{str(exception)}"
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
