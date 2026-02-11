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
from settings_handler import config_get
from language_handler import _

logger = logging.getLogger(__name__)


class InfoCache:
    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
        self.lock = threading.Lock()

    def get(self, url):
        with self.lock:
            if url in self.cache:
                info, timestamp = self.cache[url]
                if time.time() - timestamp < self.ttl:
                    return info
                else:
                    del self.cache[url]
        return None

    def set(self, url, info):
        with self.lock:
            self.cache[url] = (info, time.time())


_info_cache = InfoCache()

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None

PLAYER_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extractor_args": {"youtube": {"player_client": ["tv"], "js_variant": "tv"}},
    "js_runtimes": {"deno": {}},
    "allowed_extractors": ["youtube", "youtube:.*"],
    "no_check_certificate": True,
}

_ydl_instances = {}
_ydl_lock = threading.Lock()


def get_ydl_instance(client, cookies_path=None):
    if not YoutubeDL:
        return None
    client_tuple = tuple(client)
    key = (client_tuple, cookies_path)
    with _ydl_lock:
        if key not in _ydl_instances:
            opts = PLAYER_OPTS.copy()
            opts["extractor_args"] = {
                "youtube": {"player_client": client, "js_variant": "tv"}
            }
            if cookies_path and os.path.exists(cookies_path):
                opts["cookiefile"] = cookies_path
            _ydl_instances[key] = YoutubeDL(opts)
        return _ydl_instances[key]


VIDEO_QUALITIES = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_QUALITIES = [64, 128, 256]


def download_yt_dlp():
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    UpdateDialog(
        wx.GetApp().GetTopWindow(),
        url,
        paths.yt_dlp_path,
        _("جاري تنزيل yt-dlp"),
    )


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
    if not os.path.exists(paths.yt_dlp_path):
        return None
    try:
        result = subprocess.run(
            [paths.yt_dlp_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def update_yt_dlp():
    current = get_yt_dlp_version()
    latest = get_latest_github_release("yt-dlp/yt-dlp")
    if not latest:
        wx.MessageBox(
            _("تعذر الحصول على معلومات التحديث من GitHub"),
            _("خطأ"),
            style=wx.ICON_ERROR,
            parent=wx.GetApp().GetTopWindow(),
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
        wx.MessageBox(
            _("تعذر الحصول على معلومات التحديث من GitHub"),
            _("خطأ"),
            style=wx.ICON_ERROR,
            parent=wx.GetApp().GetTopWindow(),
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
    if not os.path.exists(paths.yt_dlp_path):
        msg = wx.MessageBox(
            _("لم يتم العثور على أداة yt-dlp.exe, هل تريد تنزيله الآن؟"),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()
            return os.path.exists(paths.yt_dlp_path)
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

        fmt = available[0]
        for f in reversed(available):
            abr = f.get("abr") or 0
            if abr <= target_abr:
                fmt = f
                break

        return fmt, None, fmt.get("abr")


class Stream:
    def __init__(self, title, url, headers=None, audio_url=None, quality=None):
        self.title = title
        self.url = url
        self.headers = headers or {}
        self.audio_url = audio_url
        self.quality = quality


def get_playable_stream(url, audio_mode=False):
    if not YoutubeDL:
        logger.error("yt-dlp is not installed")
        if audio_mode:
            return get_audio_stream(url)
        return get_video_stream(url)

    if audio_mode:
        clients_to_try = [["android"], ["web"], ["ios"], ["mweb"]]
    else:
        clients_to_try = [
            ["tv"],
            ["web_embedded"],
            ["android"],
            ["web"],
            ["ios"],
            ["mweb"],
        ]

    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    last_exception = None
    cookies_path = config_get("cookiespath")
    for client in clients_to_try:
        try:
            ydl = get_ydl_instance(client, cookies_path)
            if "youtube.com" not in url and "youtu.be" not in url:
                url = f"https://www.youtube.com/watch?v={url}"

            with _ydl_lock:
                try:
                    entry = ydl.extract_info(url, download=False)
                except Exception as e:
                    if "format" in str(e).lower():
                        with YoutubeDL(
                            {
                                "quiet": True,
                                "no_warnings": True,
                                "js_runtimes": {"deno": {}},
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
                continue

            headers = {}
            headers.update(entry.get("http_headers", {}) or {})
            headers.update(fmt.get("http_headers", {}) or {})
            headers.setdefault("User-Agent", "libmpv")

            audio_url = audio_fmt.get("url") if audio_fmt else None
            return Stream(title, url_to_play, headers, audio_url, quality=quality)
        except Exception as e:
            last_exception = e
            logger.warning(f"Failed to get stream with client {client}: {e}")
            if "restricted" in str(e).lower() or "sign in" in str(e).lower():
                continue
            else:
                break

    logger.error(f"Error in get_playable_stream: {last_exception}")
    return None


def get_media_info(url):
    cached = _info_cache.get(url)
    if cached:
        return cached

    if not YoutubeDL:
        if not os.path.exists(paths.yt_dlp_path):
            return None
        clients_to_try = ["tv", "web_embedded", "android", "web", "ios", "mweb"]
        last_err = ""
        for client in clients_to_try:
            try:
                env = os.environ.copy()
                env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
                command = [
                    paths.yt_dlp_path,
                    "-j",
                    url,
                    "--js-runtime",
                    "deno",
                    "--extractor-args",
                    f"youtube:player_client={client};js_variant=tv",
                ]
                cookies_path = config_get("cookiespath")
                if cookies_path and os.path.exists(cookies_path):
                    command.extend(["--cookies", cookies_path])
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    env=env,
                )
                if result.returncode != 0:
                    last_err = result.stderr
                    continue
                info = json.loads(result.stdout)
                _info_cache.set(url, info)
                return info
            except Exception as e:
                last_err = str(e)
                continue
        return None

    clients_to_try = [["tv"], ["web_embedded"], ["android"], ["web"], ["ios"], ["mweb"]]
    last_err = None
    cookies_path = config_get("cookiespath")

    for client in clients_to_try:
        try:
            ydl = get_ydl_instance(client, cookies_path)
            with _ydl_lock:
                info = ydl.extract_info(url, download=False)
            _info_cache.set(url, info)
            return info
        except Exception as e:
            last_err = e
            continue

    if last_err:
        logger.error(f"get_media_info failed for all clients. Last error: {last_err}")
    return None


def get_audio_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    preferred = int(config_get("defaultaudioquality"))
    stream, audio_stream, quality = pick_best_format(
        formats, preferred, is_video=False
    )
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
            if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("abr") is not None
        ]
    return sorted(list(set(available)))


def get_specific_quality_stream(url, height, audio_mode=False):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    stream, audio_stream, quality = pick_best_format(
        formats, 0, is_video=not audio_mode, target_height=height if not audio_mode else None
    )
    if audio_mode:
        # For audio, target_height is not really height but we might want to handle it
        # Actually pick_best_format for audio doesn't support target_height yet
        # But we can pass preferred_index
        # Let's just find the closest abr if audio_mode
        if isinstance(height, int):
            for f in formats:
                if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("abr") == height:
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

    if not parts and total_seconds == 0:
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


def youtube_regexp(string):
    pattern = re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
    )
    return pattern.search(string)


def check_for_updates(quiet=False):
    url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update_info.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            if not quiet:
                wx.MessageBox(
                    _(
                        "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                    ),
                    _("خطأ"),
                    parent=wx.GetApp().GetTopWindow(),
                    style=wx.ICON_ERROR,
                )
            return
        info = r.json()
        if application.version != info["version"]:
            message = wx.MessageBox(
                _("هناك تحديث جديد متوفر. هل ترغب في تنزيله الآن؟"),
                _("تحديث جديد"),
                parent=wx.GetApp().GetTopWindow(),
                style=wx.YES_NO,
            )
            url = info["url"]
            if message == wx.YES:
                from gui.update_dialog import UpdateDialog

                wx.CallAfter(UpdateDialog, wx.GetApp().GetTopWindow(), url)
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
            wx.MessageBox(
                _(
                    "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                ),
                _("خطأ"),
                parent=wx.GetApp().GetTopWindow(),
                style=wx.ICON_ERROR,
            )
