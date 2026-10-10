"""Concrete YouTube Music views built on :class:`CollectionView`.

Each factory returns a ready view controller whose ``fetch`` closure calls the
shared :class:`YTMusicService` and normalises the payload into rows. The panel
pushes these onto its navigation stack.
"""

import logging

from language_handler import _

from . import adapters
from .base_view import STATUS_AUTH, CollectionView
from .errors import AuthRequiredError
from .service import get_service

logger = logging.getLogger(__name__)


class HomeView(CollectionView):
    """The YouTube Music home feed (personalised; needs auth)."""

    def __init__(self, panel):
        super().__init__(panel, _("الرئيسية"), self._fetch_home)

    def _fetch_home(self):
        sections = get_service().get_home(limit=5) or []
        rows = []
        for section in sections:
            if isinstance(section, dict):
                rows.extend(adapters.normalize_items(section.get("contents")))
        return rows


def _playlist_tracks(data):
    data = data or {}
    return adapters.normalize_items(data.get("tracks"))


def album_view(panel, row):
    browse_id = row.get("browseId")
    audio_playlist_id = row.get("playlistId")
    title = row.get("title") or _("الألبوم")

    def fetch():
        service = get_service()
        bid = browse_id
        if not bid and audio_playlist_id:
            bid = service.get_album_browse_id(audio_playlist_id)
        data = service.get_album(bid) if bid else {}
        return adapters.normalize_items((data or {}).get("tracks"))

    return CollectionView(panel, title, fetch)


def playlist_view(panel, row):
    playlist_id = row.get("playlistId") or row.get("browseId")
    title = row.get("title") or _("قائمة التشغيل")

    def fetch():
        data = get_service().get_playlist(playlist_id)
        return _playlist_tracks(data)

    view = CollectionView(panel, title, fetch)
    view.owner_playlist_id = playlist_id
    return view


def artist_view(panel, row):
    channel_id = (
        row.get("browseId") or row.get("channel", {}).get("url", "").rsplit("/", 1)[-1]
    )
    title = row.get("title") or row.get("channel", {}).get("name") or _("الفنان")

    def fetch():
        data = get_service().get_artist(channel_id) or {}
        rows = []
        for key in ("songs", "singles", "albums", "videos", "related"):
            section = data.get(key)
            if isinstance(section, dict):
                rows.extend(adapters.normalize_items(section.get("results")))
        return rows

    return CollectionView(panel, title, fetch)


def search_view(panel, query, filter=None):
    title = _("نتائج البحث: {query}").format(query=query)

    def fetch():
        items = get_service().search(query, filter=filter)
        return adapters.normalize_items(items)

    return CollectionView(panel, title, fetch)


def library_view(panel, kind):
    """A library section. ``kind`` selects the service call + title."""
    service_calls = {
        "playlists": (
            _("قوائم التشغيل في المكتبة"),
            lambda s: s.get_library_playlists(),
        ),
        "songs": (_("الأغاني في المكتبة"), lambda s: s.get_library_songs()),
        "albums": (_("الألبومات في المكتبة"), lambda s: s.get_library_albums()),
        "artists": (_("الفنانون في المكتبة"), lambda s: s.get_library_artists()),
        "subscriptions": (_("الاشتراكات"), lambda s: s.get_library_subscriptions()),
        "liked": (
            _("الأغاني المفضلة"),
            lambda s: (s.get_liked_songs() or {}).get("tracks"),
        ),
        "history": (_("سجل الاستماع"), lambda s: s.get_history()),
    }
    title, caller = service_calls.get(kind, (_("المكتبة"), lambda s: []))

    def fetch():
        return adapters.normalize_items(caller(get_service()))

    view = CollectionView(panel, title, fetch)
    if kind == "history":
        view.section = "history"
    return view


def moods_view(panel):
    """Mood/genre categories; selecting one drills into its playlists."""
    title = _("الأجواء والأنواع")

    def fetch():
        data = get_service().get_mood_categories() or {}
        rows = []
        for category_items in data.values():
            for entry in category_items or []:
                if isinstance(entry, dict) and entry.get("params"):
                    rows.append(
                        {
                            "type": "mood",
                            "title": entry.get("title", ""),
                            "subtitle": "",
                            "videoId": None,
                            "browseId": None,
                            "playlistId": None,
                            "setVideoId": None,
                            "channel": {"name": "", "url": ""},
                            "feedbackTokens": None,
                            "duration": None,
                            "views": None,
                            "thumbnails": [],
                            "params": entry["params"],
                        }
                    )
        return rows

    view = CollectionView(panel, title, fetch)
    return view


def mood_playlists_view(panel, params, title):
    def fetch():
        items = get_service().get_mood_playlists(params)
        return adapters.normalize_items(items)

    return CollectionView(panel, title or _("الأجواء"), fetch)


def classify_load_error(exc):
    """Map a fetch exception to a view status."""
    if isinstance(exc, AuthRequiredError):
        return STATUS_AUTH
    return None
