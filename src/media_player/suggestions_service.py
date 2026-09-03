import asyncio
import logging
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

# Ensure real py_yt package is loaded if a mock was previously set in sys.modules
if "py_yt" in sys.modules and not hasattr(sys.modules["py_yt"], "__path__"):
    del sys.modules["py_yt"]

from py_yt import Recommendations
from py_yt.core.recommendations import RelatedVideosCore

logger = logging.getLogger(__name__)

# Ensure camelCase aliases as requested
if not hasattr(Recommendations, "getRelated"):
    Recommendations.getRelated = Recommendations.get_related
if not hasattr(Recommendations, "getHome"):
    Recommendations.getHome = Recommendations.get_home


def extract_video_id(url: str) -> str | None:
    if not url:
        return None
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[1].split("/")[0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[1].split("/")[0]
    return None


def parse_lockup_view_model(item: dict[str, Any]) -> dict[str, Any] | None:
    vm = item.get("lockupViewModel")
    if not isinstance(vm, dict):
        return None

    content_id = vm.get("contentId")
    if not content_id:
        return None

    meta = (vm.get("metadata") or {}).get("lockupMetadataViewModel") or {}
    title = ((meta.get("title") or {}).get("content")) or ""

    channel_name = ""
    rows = ((meta.get("metadata") or {}).get("contentMetadataViewModel") or {}).get(
        "metadataRows"
    ) or []
    if rows and len(rows) > 0:
        first_row = rows[0]
        parts = (
            first_row.get("metadataParts") if isinstance(first_row, dict) else None
        ) or []
        if parts and isinstance(parts[0], dict):
            channel_name = ((parts[0].get("text") or {}).get("content")) or ""

    duration = ""
    overlays = ((vm.get("contentImage") or {}).get("thumbnailViewModel") or {}).get(
        "overlays"
    ) or []
    for overlay in overlays:
        if not isinstance(overlay, dict):
            continue
        bottom_overlay = overlay.get("thumbnailBottomOverlayViewModel") or {}
        badges = bottom_overlay.get("badges") or []
        for badge in badges:
            if not isinstance(badge, dict):
                continue
            badge_text = (badge.get("thumbnailBadgeViewModel") or {}).get("text")
            if badge_text:
                duration = badge_text
                break
        if duration:
            break

    views = None
    if len(rows) > 1:
        second_row = rows[1]
        parts2 = (
            second_row.get("metadataParts") if isinstance(second_row, dict) else None
        ) or []
        if parts2 and isinstance(parts2[0], dict):
            views = (parts2[0].get("text") or {}).get("content")

    return {
        "id": content_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={content_id}",
        "duration": duration,
        "channel": {
            "name": channel_name,
            "url": f"https://www.youtube.com/channel/{content_id}",
        },
        "views": views,
    }


def parse_compact_video(item: dict[str, Any]) -> dict[str, Any] | None:
    video = item.get("compactVideoRenderer") or item.get("videoWithContextRenderer")
    if not isinstance(video, dict):
        return None

    content_id = video.get("videoId")
    if not content_id:
        return None

    title = ""
    title_obj = video.get("title")
    if isinstance(title_obj, dict) and "simpleText" in title_obj:
        title = title_obj["simpleText"]
    else:
        headline_obj = video.get("headline")
        if isinstance(headline_obj, dict) and headline_obj.get("runs"):
            runs = headline_obj["runs"]
            if runs and isinstance(runs[0], dict):
                title = runs[0].get("text", "")

    channel_name = ""
    byline = (video.get("shortBylineText") or {}).get("runs") or []
    if byline and isinstance(byline[0], dict):
        channel_name = byline[0].get("text", "")

    duration = ""
    length_text = video.get("lengthText") or {}
    if isinstance(length_text, dict):
        if "simpleText" in length_text:
            duration = length_text["simpleText"]
        elif length_text.get("runs"):
            runs = length_text["runs"]
            if runs and isinstance(runs[0], dict):
                duration = runs[0].get("text", "")

    return {
        "id": content_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={content_id}",
        "duration": duration,
        "channel": {
            "name": channel_name,
            "url": f"https://www.youtube.com/channel/{content_id}",
        },
        "views": None,
    }


class SuggestionsService:
    @staticmethod
    async def fetch_related_async(
        url: str, limit: int = 20, continuation: str | None = None
    ) -> dict[str, Any]:
        video_id = extract_video_id(url)
        if not video_id and not continuation:
            return {"videos": [], "continuation": None}

        try:
            core = RelatedVideosCore(
                video_link=url,
                limit=limit,
            )
            core.continuationKey = continuation
            await core._make_request()

            raw_source = core.responseSource or {}
            contents = []
            continuation_token = None

            if not continuation:
                contents = (
                    core._get_value(
                        raw_source,
                        [
                            "contents",
                            "twoColumnWatchNextResults",
                            "secondaryResults",
                            "secondaryResults",
                            "results",
                        ],
                    )
                    or []
                )
            else:
                actions = (
                    core._get_value(raw_source, ["onResponseReceivedEndpoints"]) or []
                )
                for action in actions:
                    if (
                        isinstance(action, dict)
                        and "appendContinuationItemsAction" in action
                    ):
                        items = (action.get("appendContinuationItemsAction") or {}).get(
                            "continuationItems"
                        ) or []
                        if isinstance(items, list):
                            contents.extend(items)

            videos: list[dict[str, Any]] = []
            for elem in contents:
                if not isinstance(elem, dict):
                    continue
                if "lockupViewModel" in elem:
                    if len(videos) < limit:
                        parsed = parse_lockup_view_model(elem)
                        if parsed and parsed["title"]:
                            videos.append(parsed)
                elif (
                    "compactVideoRenderer" in elem or "videoWithContextRenderer" in elem
                ):
                    if len(videos) < limit:
                        parsed = parse_compact_video(elem)
                        if parsed and parsed["title"]:
                            videos.append(parsed)
                elif "continuationItemRenderer" in elem:
                    token = core._get_value(
                        elem,
                        [
                            "continuationItemRenderer",
                            "continuationEndpoint",
                            "continuationCommand",
                            "token",
                        ],
                    )
                    if token:
                        continuation_token = str(token)

                if len(videos) >= limit and continuation_token:
                    break

            return {
                "videos": videos,
                "continuation": continuation_token,
            }
        except Exception as e:
            logger.debug(f"Error fetching related videos for {url}: {e}", exc_info=True)
            return {"videos": [], "continuation": None}

    @staticmethod
    def fetch_related(
        url: str, limit: int = 20, continuation: str | None = None
    ) -> dict[str, Any]:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    SuggestionsService.fetch_related_async(
                        url, limit=limit, continuation=continuation
                    )
                )
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            logger.debug(f"Failed in sync fetch_related wrapper: {e}", exc_info=True)
            return {"videos": [], "continuation": None}
