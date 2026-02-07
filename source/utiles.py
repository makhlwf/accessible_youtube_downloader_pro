import re
import requests
import wx
import application
import paths
from gui.update_dialog import UpdateDialog
import subprocess
import json
import os
from settings_handler import config_get
from language_handler import _

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
}

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
    except Exception:
        pass
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
            # Deno version output usually looks like:
            # deno 1.40.2 (release, x86_64-pc-windows-msvc)
            # v8 12.1.285.27
            # typescript 5.3.3
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

        # Look for any video stream
        available = [
            f
            for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]

        if not available:
            return None, None

        # Sort available by height
        available.sort(key=lambda x: x.get("height", 0))

        fmt = None
        if target_height is not None:
            match = [f for f in available if f.get("height") == target_height]
            if match:
                fmt = match[0]

        if not fmt:
            # Find the index of preferred_val in target_list
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

            # Try from preferred downwards
            for i in range(pref_idx, -1, -1):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        if not fmt:
            # If not found, try from preferred upwards
            for i in range(pref_idx + 1, len(target_list)):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        # Final fallback: best available
        if not fmt:
            fmt = available[-1]

        # If it's a DASH format (no audio), find best audio
        audio_fmt = None
        if fmt.get("acodec") == "none":
            audio_formats = [
                f
                for f in formats
                if f.get("acodec") != "none" and f.get("vcodec") == "none"
            ]
            if audio_formats:
                # Sort by abr
                audio_formats.sort(key=lambda x: x.get("abr") or 0)
                # Take best audio
                audio_fmt = audio_formats[-1]

        return fmt, audio_fmt
    else:
        # Audio
        available = [
            f
            for f in formats
            if f.get("acodec") != "none"
            and f.get("vcodec") == "none"
            and f.get("abr") is not None
        ]
        if not available:
            # Fallback to any audio
            available = [f for f in formats if f.get("acodec") != "none"]
        if not available:
            return None

        available.sort(key=lambda x: x.get("abr") or 0)

        # Audio levels are simpler. 0: low, 1: med, 2: high
        # We can map them to abr targets
        target_abr = AUDIO_QUALITIES[preferred_index]

        # Try to find closest abr <= target
        for f in reversed(available):
            abr = f.get("abr") or 0
            if abr <= target_abr:
                return f

        # If all are higher, take the lowest available
        return available[0]


class Stream:
    def __init__(self, title, url, headers=None, audio_url=None):
        self.title = title
        self.url = url
        self.headers = headers or {}
        self.audio_url = audio_url


def get_playable_stream(url, audio_mode=False):
    if not YoutubeDL:
        if audio_mode:
            return get_audio_stream(url)
        return get_video_stream(url)  # Fallback if library missing

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

    # Ensure deno is in the path for yt-dlp
    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    last_exception = None
    for client in clients_to_try:
        try:
            opts = PLAYER_OPTS.copy()
            # If audio mode, we use different extractor args if needed,
            # but mainly we just pick the best audio format later.
            opts["extractor_args"] = {
                "youtube": {"player_client": client, "js_variant": "tv"}
            }
            cookies_path = config_get("cookiespath")
            if cookies_path and os.path.exists(cookies_path):
                opts["cookiefile"] = cookies_path

            with YoutubeDL(opts) as ydl:
                # Check if it's already a direct URL or ID
                if "youtube.com" not in url and "youtu.be" not in url:
                    # Assume ID
                    url = f"https://www.youtube.com/watch?v={url}"

                try:
                    entry = ydl.extract_info(url, download=False)
                except Exception as e:
                    # If it's a format error, try again with absolute defaults
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
                    stream_fmt = pick_best_format(
                        formats, preferred_audio, is_video=False
                    )
                    # For audio mode pick_best_format returns single format dict, not tuple
                    fmt = stream_fmt
                    audio_fmt = None
                else:
                    preferred_video = int(config_get("defaultvideoquality"))
                    fmt, audio_fmt = pick_best_format(
                        formats, preferred_video, is_video=True
                    )

                # Final fallback: best single stream found by yt-dlp
                if not fmt:
                    fmt = entry

                title = entry.get("title")
                url_to_play = fmt.get("url")

                if not url_to_play:
                    continue

                # Headers
                headers = {}
                headers.update(entry.get("http_headers", {}) or {})
                headers.update(fmt.get("http_headers", {}) or {})
                headers.setdefault("User-Agent", "libmpv")

                audio_url = audio_fmt.get("url") if audio_fmt else None

                return Stream(title, url_to_play, headers, audio_url)
        except Exception as e:
            last_exception = e
            if "restricted" in str(e).lower() or "sign in" in str(e).lower():
                continue  # Try next client
            else:
                break  # Non-restriction error, stop trying

    print(f"Error in get_playable_stream: {last_exception}")
    return None


def get_media_info(url):
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
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            last_err = str(e)
            continue

    if last_err:
        print(f"get_media_info failed for all clients. Last error: {last_err}")
    return None


def get_audio_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    preferred = int(config_get("defaultaudioquality"))
    stream = pick_best_format(formats, preferred, is_video=False)
    if stream:
        return Stream(title, stream["url"])
    return None


def get_video_stream(url):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    preferred = int(config_get("defaultvideoquality"))
    stream, audio_stream = pick_best_format(formats, preferred, is_video=True)

    if stream:
        audio_url = audio_stream.get("url") if audio_stream else None
        return Stream(title, stream["url"], audio_url=audio_url)
    return None


def get_available_qualities(url):
    info = get_media_info(url)
    if info is None:
        return []
    formats = info.get("formats", [])
    # Filter for any video streams
    available = [
        f.get("height")
        for f in formats
        if f.get("vcodec") != "none" and f.get("height") is not None
    ]
    # Deduplicate and sort
    return sorted(list(set(available)))


def get_specific_quality_stream(url, height):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    stream, audio_stream = pick_best_format(
        formats, 0, is_video=True, target_height=height
    )
    if stream:
        audio_url = audio_stream.get("url") if audio_stream else None
        return Stream(title, stream["url"], audio_url=audio_url)
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
            print(f"Deno error: {result.stderr}")
            return {"videos": [], "continuation": None}
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        print(f"Error getting home feed: {e}")
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
            print(f"Deno error: {result.stderr}")
            return {"videos": [], "continuation": None}
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        print(f"Error getting watch history: {e}")
        return {"videos": [], "continuation": None}


def update_watch_history(url, watched_seconds=0):
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        return

    # Extract video ID from URL
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
        print(f"Error updating watch history: {e}")


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

    if (
        seconds > 0 or (not parts and total_seconds == 0)
    ):  # Include seconds if no other parts, or if it's the only part and total_seconds is 0
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
            return None  # Invalid format
    except ValueError:
        return None  # Handle cases where parts are not valid integers
    return total_seconds


def youtube_regexp(string):
    pattern = re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
    )  # youtube links regular expression pattern
    return pattern.search(string)


def check_for_updates(quiet=False):
    url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update_info.json"
    try:
        r = requests.get(url)
        if r.status_code != 200:
            wx.MessageBox(
                _(
                    "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                ),
                _("خطأ"),
                parent=wx.GetApp().GetTopWindow(),
                style=wx.ICON_ERROR,
            ) if not quiet else None
            return
        info = r.json()
        if application.version != info["version"]:
            print(info)
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
        wx.MessageBox(
            _("أنت تعمل الآن على آخر تحديث متوفر من التطبيق"),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        ) if not quiet else None
    except requests.ConnectionError:
        wx.MessageBox(
            _(
                "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
            ),
            _("خطأ"),
            parent=wx.GetApp().GetTopWindow(),
            style=wx.ICON_ERROR,
        ) if not quiet else None
