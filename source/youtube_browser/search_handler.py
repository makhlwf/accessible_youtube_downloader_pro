from py_yt import (
    Playlist,
    VideosSearch,
    PlaylistsSearch,
)
from utiles import time_formatting, time_to_seconds
from language_handler import _


class PlaylistResult:
    def __init__(self, url):
        self.url = url
        self.videos = []
        self.count = 0
        self.new_videos = 0
        self.title = ""
        self.videos_data = []  # To store the raw video data from Playlist.getVideos()

    async def init_async(self):
        playlist_data = await Playlist.getVideos(self.url)
        self.videos_data = playlist_data.get("videos", [])
        self.title = playlist_data.get("title", "")
        # If the title is not available in playlist_data, try to get it from the first video
        if not self.title and self.videos_data:
            self.title = self.videos_data[0].get("playlistTitle", "")
        await self.parse()
        return self

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
                video_count_str = item.get("videoCount", "0 videos")
                try:
                    video_count = int(video_count_str.split(" ")[0])
                except (ValueError, IndexError):
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
                    "elements": None,
                    "channel": {
                        "name": item.get("channel", {}).get("name"),
                        "url": item.get("channel", {}).get("link"),
                    },
                    "views": views,
                    "stream": None,
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

    def get_stream(self, number):
        return self.results[number + 1].get("stream")

    def set_stream(self, number, stream):
        self.results[number + 1]["stream"] = stream

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
            return _("مباشر")  # or _("غير معروف") depending on context of None duration
