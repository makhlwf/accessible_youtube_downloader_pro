import asyncio
from py_yt import (
    Playlist,
    Video,
    Search,
    VideosSearch,
    ChannelsSearch,
    PlaylistsSearch,
    CustomSearch,
)
from py_yt.core.constants import VideoSortOrder
from utiles import time_formatting


class PlaylistResult:
    def __init__(self, url):
        self.url = url
        self.playlist = None
        self.videos = []
        self.count = 0
        self.new_videos = 0
        self.title = ""

    async def init_async(self):
        playlist_info = await Playlist.getInfo(self.url)
        self.title = playlist_info.get('title', '')
        self.playlist = Playlist(self.url)
        if self.playlist.hasMoreVideos:
            await self.playlist.getNextVideos()
        await self.parse()
        return self

    async def parse(self):
        # py_yt.Playlist.videos is a list of Video objects after init() or next()
        current_videos_len = len(self.videos)
        for vid in self.playlist.videos[current_videos_len:]:
            video = {
                "title": vid.get("title"),
                "url": vid.get("link"),
                "duration": str(
                    vid.get("duration")
                ),  # py_yt gives duration in seconds, time_formatting expects "HH:MM:SS"
                "channel": {
                    "name": vid.get("channel", {}).get("name"),
                    "url": vid.get("channel", {}).get("link"),
                },
            }
            self.videos.append(video)
            self.count = len(self.videos)

    async def next(self):
        if not self.playlist.hasMoreVideos:
            return False

        await self.playlist.getNextVideos()
        current = self.count
        await self.parse()
        self.new_videos = self.count - current

        return True

    def get_new_titles(self):
        titles = self.get_display_titles()
        return titles[len(titles) - self.new_videos : len(titles)]

    def get_title(self, n):
        return self.videos[n]["title"]

    def get_display_titles(self):
        titles = []
        for vid in self.videos:
            title = [
                vid["title"],
                _("المدة: {}").format(
                    time_formatting(vid["duration"])
                ),  # Convert duration for display
                f"{_('بواسطة')} {vid['channel']['name']}",
            ]
            titles.append(", ".join([element for element in title if element != ""]))
        return titles

    def get_url(self, n):
        return self.videos[n]["url"]


class Search:
    def __init__(self, query, filter=0):
        self.query = query
        self.filter = filter
        self.results = {}
        self.count = 0
        self.new_videos = 0

        if self.filter == 0:  # Videos
            self.search = VideosSearch(self.query, limit=20, language="en", region="US")
        elif self.filter == 4:  # Playlists
            self.search = PlaylistsSearch(
                self.query, limit=20, language="en", region="US"
            )
        else:
            self.search = VideosSearch(self.query, limit=20, language="en", region="US")

    async def init_async(self):
        try:
            result = await self.search.next()
        except TypeError:
            result = {"result": []}  # Return an empty result
        await self.parse_results(result)
        return self

    async def parse_results(self, result):
        items = result.get("result", [])
        if isinstance(self.search, PlaylistsSearch):
            for item in items:
                video_count_str = item.get('videoCount', '0 videos')
                try:
                    video_count = int(video_count_str.split(' ')[0])
                except (ValueError, IndexError):
                    video_count = 0
                self.count += 1
                self.results[self.count] = {
                    "type": "playlist",
                    "title": item.get('title'),
                    "url": item.get('link'),
                    "duration": None,
                    "elements": video_count,
                    "channel": {
                        "name": item.get('channel', {}).get('name'),
                        "url": item.get('channel', {}).get('link'),
                    },
                    "views": None,
                }
        else: # VideosSearch, CustomSearch (assuming it returns videos)
            for item in items:
                self.count += 1
                self.results[self.count] = {
                    "type": "video",
                    "title": item.get('title'),
                    "url": item.get('link'),
                    "duration": item.get('duration'), # in seconds
                    "elements": None,
                    "channel": {
                        "name": item.get('channel', {}).get('name'),
                        "url": item.get('channel', {}).get('link'),
                    },
                    "views": item.get('view_count'),
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
                ]
            elif data["type"] == "playlist":
                title += [
                    _("قائمة تشغيل"),
                    f"{_('بواسطة')} {data['channel']['name']}",
                    _("تحتوي على {} من الفيديوهات").format(data["elements"]),
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

    async def load_more(self):
        if not self.search.has_more_results():  # Check if there are more results
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
        if data is not None:
            # Parse MM:SS or HH:MM:SS string to total seconds
            parts = str(data).split(":")
            total_seconds = 0
            try:
                if len(parts) == 3:  # HH:MM:SS
                    total_seconds = (
                        int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    )
                elif len(parts) == 2:  # MM:SS
                    total_seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 1:  # SS
                    total_seconds = int(parts[0])
                else:
                    return _("غير معروف")  # Invalid format
            except ValueError:
                return _("غير معروف")  # Handle cases where parts are not valid integers

            return _("المدة: {}").format(time_formatting(total_seconds))
        else:
            return _("مباشر") # or _("غير معروف") depending on context of None duration
