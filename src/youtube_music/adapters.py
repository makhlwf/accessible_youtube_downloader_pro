"""Normalise ytmusicapi payloads into HexPlayer's row/result model.

ytmusicapi returns many slightly different item shapes (songs, videos, albums,
artists, playlists) across endpoints. :func:`normalize_item` flattens any of
them into the single row dict the views render and that :class:`YTMusicResult`
feeds to ``MediaGui``. ``YTMusicResult`` implements the same duck-typed
protocol as ``youtube_browser.search_handler.SimpleResult`` so the existing
player queue, scraper prefetch, and favourites/history all work unchanged.
"""

WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
CHANNEL_URL = "https://www.youtube.com/channel/{channel_id}"


def _stream_key(audio_mode):
    return "audio_stream" if audio_mode else "video_stream"


def _join_artists(artists):
    names = []
    for artist in artists or []:
        if isinstance(artist, dict):
            name = artist.get("name")
        else:
            name = str(artist)
        if name:
            names.append(name)
    return ", ".join(names)


def _primary_channel(artists):
    """Return ``{"name", "url"}`` for the first artist that carries an id."""
    for artist in artists or []:
        if isinstance(artist, dict) and artist.get("id"):
            return {
                "name": artist.get("name", ""),
                "url": CHANNEL_URL.format(channel_id=artist["id"]),
            }
    # Fall back to a name-only channel (no navigable url).
    name = _join_artists(artists)
    return {"name": name, "url": ""}


def _duration(item):
    return item.get("duration") or item.get("length") or None


def _classify(item):
    """Best-effort type for a raw ytmusicapi item."""
    explicit = str(item.get("resultType") or item.get("type") or "").lower()
    if explicit in {"song", "video", "album", "artist", "playlist", "single", "ep"}:
        if explicit in {"single", "ep"}:
            return "album"
        return explicit
    if item.get("videoId"):
        return "song"
    browse_id = item.get("browseId") or ""
    if browse_id.startswith("MPRE"):
        return "album"
    if browse_id.startswith(("UC", "MPLA")):
        return "artist"
    if item.get("playlistId"):
        return "playlist"
    return "unknown"


def normalize_item(item):
    """Flatten a raw ytmusicapi item into a row dict, or ``None`` if unusable."""
    if not isinstance(item, dict):
        return None
    artists = item.get("artists") or ([item["artist"]] if item.get("artist") else [])
    channel = _primary_channel(artists)
    album = item.get("album")
    album_name = album.get("name") if isinstance(album, dict) else (album or "")
    row = {
        "type": _classify(item),
        "title": item.get("title") or item.get("name") or "",
        "subtitle": _join_artists(artists) or album_name or "",
        "videoId": item.get("videoId"),
        "browseId": item.get("browseId"),
        "playlistId": item.get("playlistId") or item.get("audioPlaylistId"),
        "setVideoId": item.get("setVideoId"),
        "channel": channel,
        "feedbackTokens": item.get("feedbackTokens"),
        "feedbackToken": item.get("feedbackToken"),
        "duration": _duration(item),
        "views": item.get("views"),
        "thumbnails": item.get("thumbnails") or [],
    }
    return row


def normalize_items(items):
    """Normalise a list, dropping unusable entries."""
    return [row for row in (normalize_item(i) for i in (items or [])) if row]


# PLACEHOLDER_RESULT


def display_title(row):
    """A single screen-reader-friendly line for a row."""
    title = row.get("title", "")
    subtitle = row.get("subtitle", "")
    duration = row.get("duration")
    parts = [title]
    if subtitle:
        parts.append(subtitle)
    line = " - ".join(p for p in parts if p)
    if duration:
        line = f"{line} ({duration})" if line else str(duration)
    return line or title


class YTMusicResult:
    """A playable queue of normalized rows, matching the SimpleResult protocol.

    Only rows that carry a ``videoId`` are playable; use :meth:`playable_only`
    to build a queue that skips albums/artists/playlists.
    """

    def __init__(self, rows):
        self.data_list = list(rows or [])
        self.count = len(self.data_list)
        self.scraper = None

    def __len__(self):
        return self.count

    @classmethod
    def playable_only(cls, rows):
        return cls([r for r in (rows or []) if r.get("videoId")])

    def get_url(self, n):
        row = self.data_list[n]
        if row.get("videoId"):
            return WATCH_URL.format(video_id=row["videoId"])
        return row.get("url", "")

    def get_title(self, n):
        return self.data_list[n].get("title", "")

    def get_stream(self, n, audio_mode=False):
        return self.data_list[n].get(_stream_key(audio_mode))

    def set_stream(self, n, stream, audio_mode=False):
        self.data_list[n][_stream_key(audio_mode)] = stream

    def get_type(self, n):
        # MediaGui treats "video" as a playable single; music items play the same.
        return "video"

    def get_channel(self, n):
        return self.data_list[n].get("channel") or {"name": "", "url": ""}

    def get_views(self, n):
        return self.data_list[n].get("views")

    def get_history_data(self, n):
        row = self.data_list[n]
        channel = self.get_channel(n)
        return {
            "title": row.get("title", ""),
            "url": self.get_url(n),
            "views": row.get("views"),
            "upload_date": "",
            "channel_name": channel.get("name", ""),
            "channel_url": channel.get("url", ""),
        }

    def get_titles(self):
        return [display_title(row) for row in self.data_list]

    def get_display_titles(self):
        return self.get_titles()
