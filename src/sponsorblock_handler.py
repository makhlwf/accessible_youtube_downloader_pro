import logging
import re
from typing import Any

import sponsorblock

from language_handler import _
from settings_handler import config_get
from youtube_url_utils import youtube_regexp

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://sponsor.ajay.app"

# Skippable categories, in the order they are listed in the settings dialog.
# See https://wiki.sponsor.ajay.app/w/Types#Category
CATEGORIES: tuple[str, ...] = (
    "sponsor",
    "selfpromo",
    "interaction",
    "intro",
    "outro",
    "preview",
    "hook",
    "filler",
    "music_offtopic",
)
DEFAULT_CATEGORIES: tuple[str, ...] = CATEGORIES

# Only "skip" segments move playback. "mute" segments, "full" segments (the whole
# video is a sponsor) and "poi" highlight markers must be left alone.
SKIPPABLE_ACTION_TYPES = frozenset({"skip"})

_client = None
_client_base_url = None


def category_labels() -> dict[str, str]:
    """Translated labels for every skippable category."""
    return {
        "sponsor": _("إعلان مدفوع"),
        "selfpromo": _("ترويج ذاتي أو طلب تبرع"),
        "interaction": _("طلب التفاعل والاشتراك"),
        "intro": _("مقدمة أو فاصل بدون محتوى"),
        "outro": _("خاتمة وبطاقات النهاية"),
        "preview": _("ملخص أو معاينة للمحتوى"),
        "hook": _("مقدمة تشويقية"),
        "filler": _("حشو ومزاح خارج الموضوع"),
        "music_offtopic": _("مقاطع غير موسيقية في الأغاني"),
    }


def category_label(category: Any) -> str:
    """Return the translated label of a category, or the raw value if unknown."""
    if not category:
        return ""
    key = str(category).casefold()
    return category_labels().get(key, str(category))


def parse_categories(value: Any) -> list[str]:
    """Normalise a stored category list into known category keys.

    An empty string means "no category selected", while a missing or invalid
    value falls back to the defaults.
    """
    if not isinstance(value, str):
        return list(DEFAULT_CATEGORIES)
    wanted = {part.strip().casefold() for part in value.split(",") if part.strip()}
    return [category for category in CATEGORIES if category in wanted]


def format_categories(categories: Any) -> str:
    """Serialise enabled categories for the settings file."""
    selected = {str(category).casefold() for category in categories or ()}
    return ",".join(category for category in CATEGORIES if category in selected)


def get_enabled_categories() -> list[str]:
    return parse_categories(config_get("sponsorblock_categories"))


def get_min_segment_duration() -> float:
    """Segments shorter than this many seconds are ignored."""
    try:
        value = float(config_get("sponsorblock_min_duration"))
    except TypeError, ValueError:
        return 0.0
    return max(0.0, value)


def get_api_base_url() -> str:
    value = config_get("sponsorblock_api_url")
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_API_URL
    return value.strip().rstrip("/")


def should_announce_skips() -> bool:
    value = config_get("sponsorblock_notify")
    return True if value is None else bool(value)


def get_sponsorblock_client() -> sponsorblock.Client:
    global _client, _client_base_url
    base_url = get_api_base_url()
    if _client is None or _client_base_url != base_url:
        _client = sponsorblock.Client(silent=True, base_url=base_url)
        _client_base_url = base_url
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


def is_skippable_segment(
    segment: Any, categories: Any = None, min_duration: float = 0.0
) -> bool:
    """Whether a segment should make the player jump forward."""
    start = getattr(segment, "start", None)
    end = getattr(segment, "end", None)
    if start is None or end is None or end <= start:
        return False
    if (end - start) < min_duration:
        return False
    action_type = getattr(segment, "action_type", None) or "skip"
    if str(action_type).casefold() not in SKIPPABLE_ACTION_TYPES:
        return False
    category = getattr(segment, "category", None)
    if categories is None or category is None:
        return True
    wanted = {str(item).casefold() for item in categories}
    return str(category).casefold() in wanted


def filter_skippable_segments(segments: Any) -> list[Any]:
    """Apply the current settings to a segment list, sorted by start time.

    Segments fetched earlier are cached with the stream, so a list may predate a
    change to the enabled categories or the minimum duration. Filtering again on
    use keeps playback in line with the settings as they are now.
    """
    if not segments:
        return []
    categories = get_enabled_categories()
    if not categories:
        return []
    min_duration = get_min_segment_duration()
    filtered = [
        segment
        for segment in segments
        if is_skippable_segment(segment, categories, min_duration)
    ]
    filtered.sort(key=lambda segment: getattr(segment, "start", 0))
    return filtered


def get_sponsorblock_segments(url_or_id: str) -> list[Any]:
    """Fetch the skip segments of a YouTube video, honouring the user settings.

    Returns a list of Segment objects (or empty list if none found or on error).
    """
    video_id = extract_video_id(url_or_id)
    if not video_id:
        logger.debug("Could not extract video ID for SponsorBlock: %s", url_or_id)
        return []

    categories = get_enabled_categories()
    if not categories:
        logger.debug("SponsorBlock is enabled but every category is turned off")
        return []

    try:
        client = get_sponsorblock_client()
        segments = client.get_skip_segments(video_id, categories=list(categories))
        valid_segments = filter_skippable_segments(segments)
        logger.info(
            "Found %d SponsorBlock segments for video %s",
            len(valid_segments),
            video_id,
        )
        return valid_segments
    except Exception as e:
        logger.warning("Failed to fetch SponsorBlock segments for %s: %s", video_id, e)
        return []


def find_skip_segment(
    current_sec: float, segments: list[Any]
) -> tuple[float, str] | None:
    """If current_sec falls within any segment, return the seek target and category.

    Handles overlapping or adjacent segments. Otherwise returns None.
    """
    if not segments or current_sec is None or current_sec < 0:
        return None

    for segment in segments:
        start = getattr(segment, "start", 0.0)
        end = getattr(segment, "end", 0.0)
        if start <= current_sec < (end - 0.05):
            target_end = end
            category = getattr(segment, "category", None)
            # Merge overlapping or contiguous segments
            for other in segments:
                other_start = getattr(other, "start", 0.0)
                other_end = getattr(other, "end", 0.0)
                if other_start <= target_end < other_end:
                    target_end = other_end
            return float(target_end), str(category) if category else ""
    return None


def find_skip_target(current_sec: float, segments: list[Any]) -> float | None:
    """Seek target in seconds if current_sec is inside a segment, else None."""
    match = find_skip_segment(current_sec, segments)
    return None if match is None else match[0]
