"""Mix playlist lookup and seed URL resolution."""

import logging
import re

from app_runtime.dependencies import ensure_deno_installed
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend.deno_service import deno_service
from youtube_backend.region import get_windows_region
from youtube_backend.session import ensure_cookies_configured

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def extract_mix_id(url):
    """Return the mix/radio playlist id (RD...) from a URL, or None.

    Anchored to the ``list=`` query parameter so it does not false-match on
    video ids that merely contain the substring ``RD``.
    """
    if not url:
        return None
    match = re.search(r"[?&]list=(RD[\w-]+)", url)
    if match:
        return match.group(1)
    return None


def is_mix_url(url):
    """True when the URL points at a YouTube Mix (auto-generated RD playlist)."""
    return extract_mix_id(url) is not None


def extract_video_id(url):
    """Return the ``v=`` video id from a watch URL, or None.

    Used to seed a mix with the specific video the user opened (optional; the
    mix can also be seeded from the playlist alone).
    """
    if not url:
        return None
    match = re.search(r"[?&]v=([\w-]{11})", url)
    if match:
        return match.group(1)
    return None


def get_mix(playlist_id, video_id=None, continuation=None, parent=None):
    """Fetch a window of a YouTube Mix (auto-generated RD playlist) via Deno.

    Mixes are infinite/personalized; pass the last played ``video_id`` to fetch
    the next window (mirrors :func:`get_shorts_feed`). Returns a dict
    ``{"videos": [...], "continuation": ...}`` (empty on failure).
    """
    feature_name = _("قائمة التشغيل المختلطة")
    if not ensure_deno_installed(parent=parent, feature_name=feature_name):
        return {"videos": [], "continuation": None}
    if not ensure_cookies_configured(parent=parent, feature_name=feature_name):
        return {"videos": [], "continuation": None}

    cookies_path = config_get("cookiespath")
    try:
        result = deno_service.send_command(
            "get_mix",
            {
                "playlistId": playlist_id,
                "videoId": video_id,
                "continuation": continuation,
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
            },
        )
        if isinstance(result, dict) and "videos" in result:
            videos = result.get("videos") or []
            logger.info(
                "get_mix ok: playlist=%s seed=%s -> %d items, continuation=%s, title=%r",
                playlist_id,
                video_id,
                len(videos),
                "yes" if result.get("continuation") else "no",
                result.get("mixTitle"),
            )
            return {
                "videos": videos,
                "continuation": result.get("continuation"),
                "mixTitle": result.get("mixTitle"),
            }
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to fetch mix: {result['error']}")
    except Exception as e:
        logger.error(f"Error fetching mix: {e}")
    return {"videos": [], "continuation": None}


# Caches a mix id -> its first real video URL so the several per-track fetchers
# (stream, media info, likes, chapters) don't each re-hit the mix endpoint.
_mix_seed_cache = {}


def resolve_mix_seed_url(url):
    """Return a directly-playable ``watch?v=<videoId>`` URL for ``url``.

    A YouTube Mix id (``RD...``) sometimes lands in the *video* slot of a URL —
    a mis-tagged related suggestion, a home-feed lockup, or a pasted mix link.
    That is not a real video, so yt-dlp/InnerTube reject it with "This video is
    unavailable". Detect that case and resolve it to the mix's first real track;
    otherwise return the URL unchanged. A genuine video id is exactly 11 chars,
    so the length guard keeps a rare RD-prefixed video id from being hijacked.
    """
    if not url:
        return url
    target = (
        url
        if ("youtube.com" in url or "youtu.be" in url)
        else f"https://www.youtube.com/watch?v={url}"
    )
    v_match = re.search(r"[?&]v=([^&]+)", target)
    v_value = v_match.group(1) if v_match else None
    mix_id = None
    if v_value and v_value.startswith("RD") and len(v_value) != 11:
        mix_id = v_value
    elif not v_value:
        # Bare mix URL (playlist?list=RD... with no seed video).
        list_match = re.search(r"[?&]list=(RD[\w-]+)", target)
        if list_match:
            mix_id = list_match.group(1)
    if not mix_id:
        return url
    if mix_id in _mix_seed_cache:
        return _mix_seed_cache[mix_id]
    mix = get_mix(mix_id)
    videos = mix.get("videos") if isinstance(mix, dict) else None
    if videos:
        seed_url = videos[0].get("url")
        if seed_url:
            _mix_seed_cache[mix_id] = seed_url
            return seed_url
    logger.error(f"Could not resolve mix {mix_id} to a playable video")
    return url
