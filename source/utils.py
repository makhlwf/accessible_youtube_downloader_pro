import sys
import re
import requests
import wx
import application
import paths
from gui.update_dialog import UpdateDialog
import subprocess
import json
import os
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from settings_handler import config_get
from language_handler import _

logger = logging.getLogger(__name__)


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
_extraction_executor = ThreadPoolExecutor(max_workers=20)


yt_dlp_module = None
YoutubeDL = None


def load_yt_dlp():
    global YoutubeDL, yt_dlp_module
    if os.path.exists(paths.yt_dlp_path):
        try:
            if paths.yt_dlp_path not in sys.path:
                sys.path.insert(0, paths.yt_dlp_path)
            if "yt_dlp" in sys.modules:
                del sys.modules["yt_dlp"]
            import yt_dlp

            yt_dlp_module = yt_dlp
            YoutubeDL = yt_dlp.YoutubeDL
            return True
        except Exception as e:
            logger.error(f"Failed to load yt-dlp from {paths.yt_dlp_path}: {e}")

    return False


load_yt_dlp()

PLAYER_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {
        "youtube": {"player_client": ["ios", "android", "web"], "js_variant": "tv"}
    },
    "js_runtimes": {"deno": {}},
    "allowed_extractors": ["youtube", "youtube:.*"],
    "no_check_certificate": True,
    "socket_timeout": 5,
}


def get_ydl_instance(client, cookies_path=None):
    """Returns a fresh YoutubeDL instance for thread-safe extraction."""
    if not YoutubeDL:
        return None
    opts = PLAYER_OPTS.copy()
    opts["extractor_args"] = {"youtube": {"player_client": client, "js_variant": "tv"}}
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    return YoutubeDL(opts)


VIDEO_QUALITIES = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_QUALITIES = [64, 128, 256]

VIDEO_QUALITY_DESCRIPTIONS = {
    144: _("144p (جودة منخفضة جدًا)"),
    240: _("240p (جودة منخفضة)"),
    360: _("360p (جودة متوسطة)"),
    480: _("480p (جودة متوسطة)"),
    720: _("720p (جودة عالية HD)"),
    1080: _("1080p (جودة عالية جدًا Full HD)"),
    1440: _("1440p (جودة فائقة 2K)"),
    2160: _("2160p (جودة فائقة 4K)"),
}


def get_quality_description(height):
    return VIDEO_QUALITY_DESCRIPTIONS.get(
        height, _("{}p (جودة غير معروفة)").format(height)
    )


def download_yt_dlp():
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    UpdateDialog(
        wx.GetApp().GetTopWindow(),
        url,
        paths.yt_dlp_path,
        _("جاري تنزيل yt-dlp"),
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
            _("تعذر الحصول على معلومات التحديث من GitHub"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من yt-dlp ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من yt-dlp\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()


def download_deno():
    url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
    UpdateDialog(
        wx.GetApp().GetTopWindow(),
        url,
        os.path.join(paths.main_path, "deno.zip"),
        _("جاري تنزيل Deno"),
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
            _("تعذر الحصول على معلومات التحديث من GitHub"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من Deno ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من Deno\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
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
            _("لم يتم العثور على مكتبة yt-dlp, هل تريد تنزيلها الآن؟"),
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
    script_path = os.path.join(bundled_path, "get_recommendations.js")
    history_script_path = os.path.join(bundled_path, "get_watch_history.js")
    config_path = os.path.join(bundled_path, "deno.json")

    if not os.path.exists(script_path) or not os.path.exists(config_path):
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
                    script_path,
                    history_script_path,
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env,
                cwd=bundled_path,
            )
        except Exception:
            pass

    import threading

    threading.Thread(target=_cache_task, daemon=True).start()


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
    def __init__(self, title, url, headers=None, audio_url=None, quality=None):
        self.title = title
        self.url = url
        self.headers = headers or {}
        self.audio_url = audio_url
        self.quality = quality


def get_playable_stream(url, audio_mode=False):
    if "youtube.com" not in url and "youtu.be" not in url:
        url_full = f"https://www.youtube.com/watch?v={url}"
    else:
        url_full = url

    cache_key = f"{url_full}_{'audio' if audio_mode else 'video'}"
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached

    if not YoutubeDL:
        logger.error("yt-dlp is not installed")
        if audio_mode:
            return get_audio_stream(url)
        return get_video_stream(url)

    if audio_mode:
        clients_to_try = [["android"], ["ios"], ["web"], ["mweb"]]
    else:
        clients_to_try = [
            ["tv"],
            ["ios"],
            ["android"],
            ["web_embedded"],
            ["web"],
            ["mweb"],
        ]

    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    url = url_full
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
                                "js_runtimes": {"deno": {}},
                                "socket_timeout": 5,
                            }
                        ) as ydl_retry:
                            entry = ydl_retry.extract_info(url, download=False)
                    else:
                        raise e

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
            return Stream(title, url_to_play, headers, audio_url, quality=quality)
        except Exception as e:
            logger.debug(f"Extraction failed for client {client}: {e}")
            return None

    # Try top clients sequentially to avoid heavy system load and lag
    for client in clients_to_try:
        result = _extract_task(client)
        if result:
            _stream_cache.set(cache_key, result)
            return result

    logger.error(f"All clients failed to extract stream for {url}")
    return None


def get_media_info(url):
    cached = _info_cache.get(url, ttl=3600)
    if cached:
        return cached

    if not YoutubeDL:
        return None

    clients_to_try = [["tv"], ["ios"], ["android"], ["web_embedded"], ["web"], ["mweb"]]
    cookies_path = config_get("cookiespath")

    def _extract_info_task(client):
        try:
            with get_ydl_instance(client, cookies_path) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    futures = [
        _extraction_executor.submit(_extract_info_task, client)
        for client in clients_to_try
    ]
    for future in as_completed(futures):
        try:
            info = future.result()
            if info:
                _info_cache.set(url, info)
                return info
        except Exception:
            continue

    logger.error(f"get_media_info failed for all clients for {url}")
    return None


def get_audio_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    preferred = int(config_get("defaultaudioquality"))
    stream, audio_stream, quality = pick_best_format(formats, preferred, is_video=False)
    if stream:
        return Stream(title, stream["url"], quality=quality)
    return None


def get_video_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    preferred = int(config_get("defaultvideoquality"))
    stream, audio_stream, quality = pick_best_format(formats, preferred, is_video=True)

    if stream:
        audio_url = audio_stream.get("url") if audio_stream else None
        return Stream(title, stream["url"], audio_url=audio_url, quality=quality)
    return None


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
    try:
        env = os.environ.copy()
        env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
        bundled_path = paths.get_bundled_data_path()
        script_path = os.path.join(bundled_path, "get_recommendations.js")
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
            cookies_path,
        ]
        if continuation:
            command.append(continuation)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=paths.main_path,
            env=env,
        )
        if result.returncode != 0:
            logger.error(f"Deno error: {result.stderr}")
            return {"videos": [], "continuation": None}
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, Exception) as e:
        logger.error(f"Error getting home feed: {e}")
        return {"videos": [], "continuation": None}


def get_watch_history(continuation=None):
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return {"videos": [], "continuation": None}
    try:
        env = os.environ.copy()
        env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
        bundled_path = paths.get_bundled_data_path()
        script_path = os.path.join(bundled_path, "get_watch_history.js")
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
            cookies_path,
        ]
        if continuation:
            command.append(continuation)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=paths.main_path,
            env=env,
        )
        if result.returncode != 0:
            logger.error(f"Deno error: {result.stderr}")
            return {"videos": [], "continuation": None}
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, Exception) as e:
        logger.error(f"Error getting watch history: {e}")
        return {"videos": [], "continuation": None}


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


def youtube_regexp(string):
    pattern = re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
    )
    return pattern.search(string)


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
            from gui.update_check_dialog import UpdateCheckDialog

            new_version = info["version"]
            whats_new = info.get("whats_new", _("لا توجد معلومات حول هذا التحديث"))
            url = info["url"]
            dlg = UpdateCheckDialog(wx.GetApp().GetTopWindow(), new_version, whats_new)
            if dlg.ShowModal() == wx.ID_OK:
                from gui.update_dialog import UpdateDialog

                wx.CallAfter(
                    UpdateDialog,
                    wx.GetApp().GetTopWindow(),
                    url,
                    _("جاري تنزيل التحديث"),
                )
            dlg.Destroy()
            return
        if not quiet:
            wx.MessageBox(
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
