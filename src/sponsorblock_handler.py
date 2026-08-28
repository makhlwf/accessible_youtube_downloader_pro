import logging
import re
from typing import Any

import sponsorblock

from youtube_url_utils import youtube_regexp

logger = logging.getLogger(__name__)

_client = None


def get_sponsorblock_client() -> sponsorblock.Client:
    global _client
    if _client is None:
        _client = sponsorblock.Client(silent=True)
    return _client


def extract_video_id(url_or_id: str) -> str | None:
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    candidate = url_or_id.strip()
    if len(candidate) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", candidate):
        return candidate
    match = youtube_regexp(candidate)
    if match:
        return match.group(5)
    match_id = re.search(
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})", candidate
    )
    if match_id:
        return match_id.group(1)
    return None


def get_sponsorblock_segments(url_or_id: str) -> list[Any]:
    """Fetch all skip segments for a YouTube video using sponsorblock.py.

    Returns a list of Segment objects (or empty list if none found or on error).
    """
    video_id = extract_video_id(url_or_id)
    if not video_id:
        logger.debug("Could not extract video ID for SponsorBlock: %s", url_or_id)
        return []

    try:
        client = get_sponsorblock_client()
        segments = client.get_skip_segments(video_id)
        if not segments:
            return []

        valid_segments = []
        for s in segments:
            start = getattr(s, "start", None)
            end = getattr(s, "end", None)
            if start is not None and end is not None and end > start:
                valid_segments.append(s)

        valid_segments.sort(key=lambda s: getattr(s, "start", 0))
        logger.info(
            "Found %d SponsorBlock segments for video %s",
            len(valid_segments),
            video_id,
        )
        return valid_segments
    except Exception as e:
        logger.warning("Failed to fetch SponsorBlock segments for %s: %s", video_id, e)
        return []


def find_skip_target(current_sec: float, segments: list[Any]) -> float | None:
    """If current_sec falls within any segment [start, end], returns the target seek time in seconds.

    Handles overlapping or adjacent segments. Otherwise returns None.
    """
    if not segments or current_sec is None or current_sec < 0:
        return None

    for segment in segments:
        start = getattr(segment, "start", 0.0)
        end = getattr(segment, "end", 0.0)
        if start <= current_sec < (end - 0.05):
            target_end = end
            # Merge overlapping or contiguous segments
            for other in segments:
                other_start = getattr(other, "start", 0.0)
                other_end = getattr(other, "end", 0.0)
                if other_start <= target_end < other_end:
                    target_end = other_end
            return float(target_end)
    return None
