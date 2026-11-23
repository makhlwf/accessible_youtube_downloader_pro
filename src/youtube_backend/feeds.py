"""YouTube feeds and local and remote watch history."""

import logging
import os
import re
import subprocess
import sys

import paths
from app_runtime.dependencies import ensure_deno_installed
from app_state.database import WatchHistory
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend.deno_service import deno_service
from youtube_backend.region import get_windows_region
from youtube_backend.session import ensure_cookies_configured
from youtube_backend.youtube_url_utils import youtube_regexp

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_home_feed(continuation=None, parent=None, *, cookies_path=None):
    """Fetch the feed, optionally using a cookie path verified by the caller."""
    if cookies_path is None:
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


def get_subscriptions_feed(continuation=None):
    """Fetch one authenticated subscriptions VIDEO page; safe on worker threads.

    No GUI, installation or cookie prompts are invoked. The JS service preserves
    FEsubscriptions' upstream newest-posted order, not a localized-date sort.
    Continuations are opaque upstream tokens, not local list offsets.
    """
    failure = {
        "videos": [],
        "continuation": None,
        "error": _(
            "Could not load subscriptions. Check your YouTube cookies and try again."
        ),
    }
    try:
        cookies_path = config_get("cookiespath")
        if not cookies_path or not os.path.isfile(cookies_path):
            return {
                **failure,
                "error": _(
                    "A valid YouTube cookies file is required for subscriptions."
                ),
            }
        if continuation is not None and (
            not isinstance(continuation, str) or not continuation.strip()
        ):
            return failure
        response = deno_service.send_command(
            "get_subscriptions_feed",
            {
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
                "continuationToken": continuation,
            },
        )
        if (
            not isinstance(response, dict)
            or "error" in response
            or not isinstance(response.get("videos"), list)
        ):
            return failure
        next_token = response.get("continuation")
        if next_token is not None and (
            not isinstance(next_token, str) or not next_token.strip()
        ):
            return failure
        videos = []
        seen = set()
        for item in response["videos"]:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id")
            title = item.get("title")
            if (
                not isinstance(video_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id)
                or not isinstance(title, str)
                or not title.strip()
                or video_id in seen
            ):
                continue
            # Copy only public display fields, never an upstream error object or
            # arbitrary service keys. Build the playable URL from the validated ID.
            video = {
                "id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "author": item.get("author")
                if isinstance(item.get("author"), str)
                else "",
                "published_time": item.get("published_time")
                if isinstance(item.get("published_time"), str)
                else "",
                "is_live": item.get("is_live") is True,
            }
            metadata = item.get("metadata_text")
            if isinstance(metadata, list) and all(
                isinstance(text, str) for text in metadata
            ):
                video["metadata_text"] = metadata.copy()
            videos.append(video)
            seen.add(video_id)
        if response["videos"] and not videos:
            return failure
        return {"videos": videos, "continuation": next_token}
    except Exception:
        # Do not log exception messages: they may carry cookies or response data.
        return failure


def get_subscribed_channels(parent=None):
    """Fetch the channels the logged-in user is subscribed to via Deno service.

    Requires a valid cookies file. Returns a dict ``{"channels": [...],
    "error": optional}`` where each channel has ``name``, ``subscribers`` and
    ``url`` keys.
    """
    feature_name = _("القنوات المشترك بها")
    result = {"channels": []}
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return result
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return result

    cookies_path = config_get("cookiespath")
    try:
        response = deno_service.send_command(
            "get_subscribed_channels",
            {
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
            },
        )
        if isinstance(response, dict) and "channels" in response:
            result["channels"] = response.get("channels") or []
            return result
        if isinstance(response, dict) and "error" in response:
            logger.error(f"Failed to fetch subscribed channels: {response['error']}")
            result["error"] = response["error"]
            return result
    except Exception as e:
        logger.error(f"Error fetching subscribed channels: {e}")
        result["error"] = str(e)
    return result
