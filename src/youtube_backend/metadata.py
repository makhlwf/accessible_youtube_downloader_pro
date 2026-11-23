"""Video reactions and chapter metadata."""

import logging
import math
import os
import re

import paths
from app_runtime.dependencies import ensure_deno_installed
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend import ytdlp_runtime
from youtube_backend.deno_service import deno_service
from youtube_backend.mixes import resolve_mix_seed_url
from youtube_backend.region import get_windows_region
from youtube_backend.session import ensure_cookies_configured
from youtube_backend.youtube_url_utils import get_video_id, youtube_regexp
from youtube_backend.ytdlp_runtime import PLAYER_OPTS

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


def validate_video_reaction(parent=None):
    feature_name = _("إبداء الإعجاب بالمرئيات")

    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return _("لم يتم تثبيت أداة Deno المطلوبة للإعجاب بالمرئيات.")

    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return _("لم يتم ضبط ملف الكوكيز الخاص بيوتيوب.")
    return None


def like_video(url, action="like", parent=None, *, cookies_path=None):
    """
    Performs a like, dislike, or remove_like interaction on a video.
    Actions: 'like', 'dislike', 'remove_like'
    Returns dict: {"success": bool, "error": str or None}
    """
    if cookies_path is None:
        error = validate_video_reaction(parent)
        if error:
            return {"success": False, "error": error}
        cookies_path = config_get("cookiespath")

    video_id = get_video_id(url)
    if not video_id:
        return {
            "success": False,
            "error": _("رابط الفيديو غير صالح."),
        }

    try:
        result = deno_service.send_command(
            "like_video",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "action": action,
                "location": get_windows_region(),
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
    url = resolve_mix_seed_url(url)
    cookies_path = config_get("cookiespath")
    video_id = get_video_id(url)
    if not video_id:
        logger.error(f"Failed to match URL: {url}")
        return _normalize_like_info(None)
    logger.info(f"Fetching likes for video_id: {video_id} with cookies: {cookies_path}")

    try:
        result = deno_service.send_command(
            "get_video_likes",
            {
                "cookiesPath": cookies_path,
                "videoId": video_id,
                "location": get_windows_region(),
            },
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
    if not ytdlp_runtime.YoutubeDL:
        return info

    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
    opts["skip_download"] = True
    opts["extract_flat"] = False
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path

    try:
        with ytdlp_runtime.YoutubeDL(opts) as ydl:
            video_info = ydl.extract_info(url, download=False)
        info["likes"] = _coerce_count(
            video_info.get("like_count") if video_info else None
        )
    except Exception as e:
        logger.error(f"Failed to fetch like count with yt-dlp fallback: {e}")
    return info


def _get_video_chapters_with_yt_dlp(url, cookies_path=None):
    if not ytdlp_runtime.YoutubeDL:
        return []

    opts = PLAYER_OPTS.copy()
    opts["js_runtimes"] = {"deno": {"path": paths.get_deno_path()}}
    opts["skip_download"] = True
    opts["extract_flat"] = False
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path

    try:
        with ytdlp_runtime.YoutubeDL(opts) as ydl:
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
    url = resolve_mix_seed_url(url)
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
