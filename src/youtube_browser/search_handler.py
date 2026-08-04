import asyncio
import logging
import os
from urllib.parse import urlsplit, urlunsplit

from py_yt import (
    ChannelsSearch,
    Playlist,
    PlaylistsSearch,
    VideosSearch,
)

import utils
from language_handler import _
from settings_handler import config_get
from utils import format_duration, time_to_seconds

logger = logging.getLogger(__name__)


CHANNEL_TAB_SUFFIXES = {
    "featured",
    "videos",
    "shorts",
    "streams",
    "live",
    "playlists",
    "community",
    "channels",
    "about",
}

CHANNEL_TABS = [
    ("home", _("الرئيسية")),
    ("videos", _("الفيديوهات")),
    ("shorts", _("المقاطع القصيرة")),
    ("live", _("البث المباشر")),
    ("playlists", _("قوائم التشغيل")),
    ("community", _("المجتمع")),
    ("channels", _("القنوات")),
    ("about", _("حول")),
]


def stream_key(audio_mode=False):
    return "audio_stream" if audio_mode else "video_stream"


def normalise_channel_url(url):
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = parts.scheme or "https"
    netloc = parts.netloc or "www.youtube.com"
    path = parts.path.rstrip("/")
    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[-1].lower() in CHANNEL_TAB_SUFFIXES:
        segments = segments[:-1]
    path = "/" + "/".join(segments) if segments else ""
    return urlunsplit((scheme, netloc, path, "", ""))


def channel_tab_url(url, tab):
    base = normalise_channel_url(url)
    suffixes = {
        "home": "",
        "videos": "videos",
        "shorts": "shorts",
        "live": "streams",
        "playlists": "playlists",
        "community": "community",
        "channels": "channels",
        "about": "about",
    }
    suffix = suffixes.get(tab, "")
    return f"{base}/{suffix}" if suffix else base


def _absolute_youtube_url(url, result_type, fallback_id=None):
    if url and url.startswith(("http://", "https://")):
        return url
    if url and url.startswith("/"):
        return f"https://www.youtube.com{url}"
    if result_type == "playlist":
        playlist_id = fallback_id or url
        return (
            f"https://www.youtube.com/playlist?list={playlist_id}"
            if playlist_id
            else ""
        )
    if result_type == "channel":
        channel_id = fallback_id or url
        if not channel_id:
            return ""
        if str(channel_id).startswith("@"):
            return f"https://www.youtube.com/{channel_id}"
        return f"https://www.youtube.com/channel/{channel_id}"
    video_id = fallback_id or url
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _channel_from_data(data, default_name="", default_url=""):
    channel = data.get("channel") if isinstance(data.get("channel"), dict) else {}
    return {
        "name": (
            channel.get("name")
            or data.get("channel_name")
            or data.get("channel")
            or data.get("uploader")
            or default_name
            or _("غير معروف")
        ),
        "url": (
            channel.get("url")
            or channel.get("link")
            or data.get("channel_url")
            or data.get("uploader_url")
            or default_url
            or ""
        ),
    }


def _yt_dlp_flat_options(start=1, end=30):
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playliststart": start,
        "playlistend": end,
        "ignoreerrors": True,
        "nocheckcertificate": True,
    }
    cookies_path = config_get("cookiespath")
    if cookies_path and os.path.exists(cookies_path):
        options["cookiefile"] = cookies_path
    return options


class PlaylistResult:
    def __init__(self, url):
        self.url = url
        self.videos = []
        self.count = 0
        self.new_videos = 0
        self.title = ""
        self.videos_data = []  # To store the raw video data from Playlist.getVideos()

    async def init_async(self):
        try:
            playlist_data = await Playlist.getVideos(self.url)
        except Exception:
            logger.debug(
                "py_yt playlist extraction failed; retrying with yt-dlp. url=%s",
                self.url,
                exc_info=True,
            )
            await asyncio.to_thread(self.load_with_yt_dlp)
            return self
        if not isinstance(playlist_data, dict):
            playlist_data = {}
        self.videos_data = playlist_data.get("videos", [])
        self.title = playlist_data.get("title", "")
        # If the title is not available in playlist_data, try to get it from the first video
        if not self.title and self.videos_data:
            self.title = self.videos_data[0].get("playlistTitle", "")
        await self.parse()
        if not self.videos and utils.YoutubeDL:
            await asyncio.to_thread(self.load_with_yt_dlp)
        return self

    def load_with_yt_dlp(self):
        if not utils.YoutubeDL:
            return
        with utils.YoutubeDL(_yt_dlp_flat_options(1, 100)) as ydl:
            info = ydl.extract_info(self.url, download=False)
        if not isinstance(info, dict):
            return
        self.title = (
            self.title
            or info.get("title")
            or info.get("playlist_title")
            or _("قائمة تشغيل")
        )
        self.videos = []
        seen_urls = set()
        for entry in info.get("entries", []) or []:
            video = self.normalise_yt_dlp_entry(entry)
            if video and video["url"] not in seen_urls:
                seen_urls.add(video["url"])
                self.videos.append(video)
        self.count = len(self.videos)
        self.new_videos = self.count

    def normalise_yt_dlp_entry(self, entry):
        if not entry:
            return None
        fallback_id = entry.get("id")
        url = _absolute_youtube_url(
            entry.get("webpage_url") or entry.get("url"),
            "video",
            fallback_id,
        )
        if not url:
            return None
        return {
            "id": fallback_id,
            "title": entry.get("title") or _("غير معروف"),
            "url": url,
            "duration": entry.get("duration") or entry.get("duration_string"),
            "channel": _channel_from_data(entry, default_name=self.title),
        }

    async def parse(self):
        # Iterate through the raw video data obtained from Playlist.getVideos()
        for vid in self.videos_data:
            duration_str = vid.get("duration")
            # Convert duration string (e.g., "MM:SS") to total seconds
            duration_seconds = time_to_seconds(duration_str) if duration_str else None
            video = {
                "id": vid.get("id"),
                "title": vid.get("title"),
                "url": vid.get("link"),
                "duration": duration_seconds,  # Store duration in seconds
                "channel": {
                    "name": vid.get("channel", {}).get("name"),
                    "url": vid.get("channel", {}).get("link"),
                },
            }
            self.videos.append(video)
        self.count = len(self.videos)  # Update count based on all parsed videos

    async def next(self):
        # Since Playlist.getVideos() fetches all videos at once, there are no more videos to load
        return False

    def get_id(self, n):
        return self.videos[n]["id"]

    def get_title(self, n):
        return self.videos[n]["title"]

    def get_display_titles(self):
        titles = []
        for vid in self.videos:
            title = [
                vid["title"],
                format_duration(vid["duration"]),
                f"{_('بواسطة')} {vid['channel']['name']}",
            ]
            titles.append(", ".join([element for element in title if element != ""]))
        return titles

    def get_url(self, n):
        return self.videos[n]["url"]

    def get_channel(self, n):
        return self.videos[n]["channel"]

    def get_views(self, n):
        return None

    def get_history_data(self, n):
        video = self.videos[n]
        return {
            "title": video["title"],
            "url": video["url"],
            "channel_name": video["channel"]["name"],
            "channel_url": video["channel"]["url"],
        }

    def get_stream(self, n, audio_mode=False):
        try:
            return self.videos[n].get(stream_key(audio_mode))
        except IndexError, KeyError:
            return None

    def set_stream(self, n, stream, audio_mode=False):
        try:
            self.videos[n][stream_key(audio_mode)] = stream
        except IndexError:
            pass

    def get_type(self, n):
        return "video"


class SimpleResult:
    def __init__(self, data_list):
        self.data_list = data_list
        self.count = len(data_list)
        self.scraper = None

    def __len__(self):
        return self.count

    def get_url(self, n):
        return self.data_list[n]["url"]

    def get_title(self, n):
        return self.data_list[n].get("title", "")

    def get_stream(self, n, audio_mode=False):
        return self.data_list[n].get(stream_key(audio_mode))

    def set_stream(self, n, stream, audio_mode=False):
        self.data_list[n][stream_key(audio_mode)] = stream

    def get_type(self, n):
        return self.data_list[n].get("type", "video")

    def get_channel(self, n):
        return _channel_from_data(self.data_list[n])

    def get_views(self, n):
        return self.data_list[n].get("views")

    def get_history_data(self, n):
        data = self.data_list[n]
        channel = self.get_channel(n)
        return {
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "views": data.get("views"),
            "upload_date": data.get("uploadDate") or data.get("upload_date", ""),
            "channel_name": channel["name"],
            "channel_url": channel["url"],
        }


class ChannelTabResult:
    def __init__(self, url, tab="videos", title=""):
        self.source_url = normalise_channel_url(url)
        self.tab = tab
        self.title = title
        self.items = []
        self.videos = self.items
        self.count = 0
        self.new_videos = 0
        self.batch_size = 30
        self.has_more = tab != "about"
        self.load()

    def load(self):
        if self.tab == "about":
            self.load_about()
            return
        if not utils.YoutubeDL:
            raise RuntimeError(_("yt-dlp is not installed"))

        start = self.count + 1
        end = self.count + self.batch_size
        url = channel_tab_url(self.source_url, self.tab)
        with utils.YoutubeDL(_yt_dlp_flat_options(start, end)) as ydl:
            info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict):
            self.title = self.title or _("قناة")
            self.new_videos = 0
            self.has_more = False
            return

        self.title = (
            self.title
            or info.get("channel")
            or info.get("uploader")
            or info.get("title")
            or _("قناة")
        )
        entries = [entry for entry in info.get("entries", []) or [] if entry]
        current = len(self.items)
        seen_urls = {item["url"] for item in self.items}
        for entry in entries:
            item = self.normalise_entry(entry)
            if item and item["url"] not in seen_urls:
                self.items.append(item)
                seen_urls.add(item["url"])

        self.count = len(self.items)
        self.new_videos = self.count - current
        if len(entries) < self.batch_size or self.new_videos == 0:
            self.has_more = False

    def load_about(self):
        self.has_more = False
        info = {}
        if utils.YoutubeDL:
            try:
                with utils.YoutubeDL(_yt_dlp_flat_options(1, 1)) as ydl:
                    info = ydl.extract_info(
                        channel_tab_url(self.source_url, "about"), download=False
                    )
            except Exception:
                info = {}
        if not isinstance(info, dict):
            info = {}
        self.title = (
            self.title
            or info.get("channel")
            or info.get("uploader")
            or info.get("title")
            or _("قناة")
        )
        rows = [
            _("القناة: {}").format(self.title),
            _("الرابط: {}").format(self.source_url),
        ]
        for key, label in (
            ("channel_follower_count", _("عدد المشتركين: {}")),
            ("view_count", _("عدد المشاهدات: {}")),
            ("description", _("الوصف: {}")),
        ):
            value = info.get(key)
            if value:
                rows.append(label.format(value))
        self.items = [
            {
                "type": "info",
                "title": row,
                "url": self.source_url,
                "duration": None,
                "views": None,
                "uploadDate": "",
                "channel": {"name": self.title, "url": self.source_url},
            }
            for row in rows
        ]
        self.videos = self.items
        self.count = len(self.items)
        self.new_videos = self.count

    def normalise_entry(self, entry):
        result_type = self.result_type(entry)
        fallback_id = entry.get("id")
        url = _absolute_youtube_url(
            entry.get("webpage_url") or entry.get("url"),
            result_type,
            fallback_id,
        )
        if not url:
            return None
        title = entry.get("title") or entry.get("channel") or entry.get("uploader")
        if not title:
            title = _("غير معروف")
        channel = _channel_from_data(
            entry,
            default_name=self.title,
            default_url=self.source_url,
        )
        if result_type == "channel":
            channel = {"name": title, "url": url}
        return {
            "type": result_type,
            "id": fallback_id,
            "title": title,
            "url": url,
            "duration": entry.get("duration") or entry.get("duration_string"),
            "views": entry.get("view_count"),
            "uploadDate": entry.get("upload_date") or entry.get("timestamp") or "",
            "elements": entry.get("playlist_count") or entry.get("n_entries"),
            "channel": channel,
            "audio_stream": None,
            "video_stream": None,
        }

    def result_type(self, entry):
        url = str(entry.get("webpage_url") or entry.get("url") or "")
        ie_key = str(entry.get("ie_key") or "")
        if self.tab == "playlists" or "playlist" in ie_key.lower() or "list=" in url:
            return "playlist"
        if self.tab == "channels" or "/channel/" in url or "/@" in url:
            return "channel"
        return "video"

    def load_more(self):
        if not self.has_more:
            return False
        self.load()
        return self.new_videos > 0

    def get_display_titles(self):
        return [self.get_display_title(item) for item in self.items]

    def get_display_title(self, item):
        if item["type"] == "video":
            parts = [
                item["title"],
                format_duration(item["duration"]) if item["duration"] else "",
                f"{_('بواسطة')} {item['channel']['name']}",
                self.views_part(item["views"]),
                str(item.get("uploadDate", "")),
            ]
        elif item["type"] == "playlist":
            parts = [
                item["title"],
                _("قائمة تشغيل"),
                f"{_('بواسطة')} {item['channel']['name']}",
                _("تحتوي على {} من الفيديوهات").format(item["elements"])
                if item.get("elements")
                else "",
            ]
        elif item["type"] == "channel":
            parts = [item["title"], _("قناة")]
        else:
            parts = [item["title"]]
        return ", ".join([part for part in parts if part])

    def get_last_titles(self):
        titles = self.get_display_titles()
        return titles[len(titles) - self.new_videos : len(titles)]

    def get_id(self, n):
        return self.items[n].get("id")

    def get_title(self, n):
        return self.items[n]["title"]

    def get_url(self, n):
        return self.items[n]["url"]

    def get_type(self, n):
        return self.items[n]["type"]

    def get_channel(self, n):
        return self.items[n]["channel"]

    def get_views(self, n):
        return self.items[n]["views"]

    def get_stream(self, n, audio_mode=False):
        return self.items[n].get(stream_key(audio_mode))

    def set_stream(self, n, stream, audio_mode=False):
        self.items[n][stream_key(audio_mode)] = stream

    def get_history_data(self, n):
        item = self.items[n]
        return {
            "title": item["title"],
            "url": item["url"],
            "views": item["views"],
            "upload_date": item.get("uploadDate", ""),
            "channel_name": item["channel"]["name"],
            "channel_url": item["channel"]["url"],
        }

    def views_part(self, data):
        if data is not None:
            return _("عدد المشاهدات {}").format(data)
        return ""


class Search:
    def __init__(self, query, filter=0):
        self.query = query
        self.filter = filter
        self.results = {}
        self.count = 0
        self.new_videos = 0

        lang = config_get("lang") or "ar"
        region = utils.get_windows_region()

        if self.filter == 0:  # Videos
            self.search = VideosSearch(
                self.query, limit=20, language=lang, region=region
            )
        elif self.filter == 4:  # Playlists
            self.search = PlaylistsSearch(
                self.query, limit=20, language=lang, region=region
            )
        elif self.filter == 5:  # Channels
            self.search = ChannelsSearch(
                self.query, limit=20, language=lang, region=region
            )
        else:
            self.search = VideosSearch(
                self.query, limit=20, language=lang, region=region
            )

    async def init_async(self):
        try:
            result = await self.search.next()
        except TypeError:
            result = {"result": []}  # Return an empty result
        await self.parse_results(result)
        return self

    async def parse_results(self, result):
        items = result.get("result", [])
        if self.filter == 4:
            for item in items:
                video_count_str = item.get("videoCount", "0")
                try:
                    video_count = int(video_count_str.split(" ")[0])
                except ValueError, IndexError:
                    video_count = 0
                self.count += 1
                self.results[self.count] = {
                    "type": "playlist",
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "duration": None,
                    "elements": video_count,
                    "channel": {
                        "name": item.get("channel", {}).get("name"),
                        "url": item.get("channel", {}).get("link"),
                    },
                    "views": None,
                }
        elif self.filter == 5:
            for item in items:
                self.count += 1
                title = (
                    item.get("title")
                    or item.get("channel", {}).get("name")
                    or _("غير معروف")
                )
                channel_url = item.get("link")
                channel_id = item.get("id")
                if not channel_url and channel_id:
                    channel_url = f"https://www.youtube.com/channel/{channel_id}"
                self.results[self.count] = {
                    "type": "channel",
                    "title": title,
                    "url": channel_url,
                    "duration": None,
                    "elements": item.get("videoCount"),
                    "subscribers": item.get("subscribers"),
                    "channel": {
                        "name": title,
                        "url": channel_url,
                    },
                    "views": None,
                }
        else:  # VideosSearch, CustomSearch (assuming it returns videos)
            for item in items:
                self.count += 1
                view_count = item.get("viewCount")
                if isinstance(view_count, dict):
                    views = view_count.get("short") or view_count.get("text")
                else:
                    views = (
                        view_count if view_count is not None else item.get("view_count")
                    )

                self.results[self.count] = {
                    "type": "video",
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "duration": item.get("duration"),  # in seconds
                    "uploadDate": item.get("publishedTime"),
                    "elements": None,
                    "channel": {
                        "name": item.get("channel", {}).get("name"),
                        "url": item.get("channel", {}).get("link"),
                    },
                    "views": views,
                    "audio_stream": None,
                    "video_stream": None,
                }

    def get_titles(self):
        titles = []
        for number in sorted(self.results.keys()):
            data = self.results[number]
            title = [data["title"]]
            if data["type"] == "video":
                title += [
                    self.get_duration(data["duration"]),
                    f"{_('بواسطة')} {data['channel']['name']}",
                    self.views_part(data["views"]),
                    str(data.get("uploadDate", "")),
                ]
            elif data["type"] == "playlist":
                title += [
                    _("قائمة تشغيل"),
                    f"{_('بواسطة')} {data['channel']['name']}",
                    _("تحتوي على {} من الفيديوهات").format(data["elements"]),
                ]
            elif data["type"] == "channel":
                title += [
                    _("قناة"),
                    data.get("subscribers") or "",
                    _("تحتوي على {} من الفيديوهات").format(data["elements"])
                    if data.get("elements")
                    else "",
                ]
            titles.append(", ".join([element for element in title if element != ""]))
        return titles

    def get_last_titles(self):
        titles = self.get_titles()
        return titles[len(titles) - self.new_videos : len(titles)]

    def get_title(self, number):
        return self.results[number + 1]["title"]

    def get_url(self, number):
        return self.results[number + 1]["url"]

    def get_type(self, number):
        return self.results[number + 1]["type"]

    def get_channel(self, number):
        return self.results[number + 1]["channel"]

    def get_stream(self, number, audio_mode=False):
        return self.results[number + 1].get(stream_key(audio_mode))

    def set_stream(self, number, stream, audio_mode=False):
        self.results[number + 1][stream_key(audio_mode)] = stream

    async def load_more(self):
        if not self.search.continuationKey:  # Check if there are more results
            return False

        try:
            result = await self.search.next()
        except TypeError:
            return False

        current = self.count
        await self.parse_results(result)
        self.new_videos = self.count - current
        return True

    def get_views(self, number):
        return self.results[number + 1]["views"]

    def views_part(self, data):
        if data is not None:
            return _("عدد المشاهدات {}").format(data)
        else:
            return _("بث مباشر")

    def get_duration(self, data):  # get the duration of the video
        return format_duration(data)
