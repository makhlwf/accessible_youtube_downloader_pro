"""YouTube comment retrieval and interactions."""

import logging
import os

import paths
from app_runtime.dependencies import ensure_deno_installed
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend import ytdlp_runtime
from youtube_backend.deno_service import deno_service
from youtube_backend.metadata import _coerce_count
from youtube_backend.session import ensure_cookies_configured
from youtube_backend.youtube_url_utils import youtube_regexp
from youtube_backend.ytdlp_runtime import PLAYER_OPTS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    if not ytdlp_runtime.YoutubeDL:
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
        with ytdlp_runtime.YoutubeDL(opts) as ydl:
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
