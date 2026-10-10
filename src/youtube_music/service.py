"""``YTMusicService`` — a thread-safe wrapper around ytmusicapi.YTMusic.

Design notes:

* ytmusicapi is synchronous ``requests``-based and NOT documented thread-safe,
  so every call is serialised per client with a lock and must run on a daemon
  thread, never the wx GUI thread.
* Two clients are built lazily: an anonymous one (always available) and an
  authenticated one (only when the browser cookie file carries auth cookies).
  ``_client(mode)`` picks between them; ``mode="auth"`` raises
  :class:`AuthRequiredError` when signed out so views can prompt a cookie import.
* Unlike the Deno ``service.js`` bridge (a single lock-serialised pipe shared
  with comments/likes/home-feed), this talks HTTP in-process, so music browse
  traffic does not contend on that pipe. Stream *resolution* still goes through
  ``utils.get_playable_stream`` (yt-dlp).
* Every public method is normalised through :func:`guard`, which maps auth
  failures to :class:`AuthRequiredError` and everything else to
  :class:`YTMusicUnavailableError` (never logging cookie values).

Upload and podcast/episode wrappers are present for completeness but are not yet
surfaced in the UI (core-music-first scope).
"""

import logging
import threading

from ytmusicapi import YTMusic

from . import auth_bridge
from .errors import AuthRequiredError, guard

logger = logging.getLogger(__name__)


def _resolve_cookies_path():
    try:
        from settings_handler import config_get

        configured = config_get("cookiespath")
    except Exception:
        configured = ""
    if configured:
        return configured
    try:
        import cookies_manager

        return cookies_manager.get_default_browser_cookies_path()
    except Exception:
        return ""


def _resolve_language():
    try:
        from settings_handler import config_get

        return config_get("lang") or "en"
    except Exception:
        return "en"


# PLACEHOLDER_SERVICE_CLASS


class YTMusicService:
    """Lazy anon + authenticated ytmusicapi clients with per-client locking."""

    def __init__(self, language="en", location="", cookies_path=None):
        self._language = language or "en"
        self._location = location or ""
        self._cookies_path = cookies_path
        self._anon = None
        self._auth = None
        self._anon_lock = threading.Lock()
        self._auth_lock = threading.Lock()
        self._build_lock = threading.Lock()

    # -- client construction -------------------------------------------------

    def _new_client(self, auth):
        """Build a YTMusic client, retrying with a safe locale on locale errors."""
        try:
            return YTMusic(auth=auth, language=self._language, location=self._location)
        except Exception as exc:
            message = str(exc).lower()
            if "language" in message or "location" in message:
                return YTMusic(auth=auth, language="en", location="")
            raise

    def _get_anon(self):
        if self._anon is None:
            with self._build_lock:
                if self._anon is None:
                    self._anon = self._new_client(None)
        return self._anon

    def _construct_auth(self, headers):
        return self._new_client(headers)

    def _get_auth(self):
        if self._auth is None:
            with self._build_lock:
                if self._auth is None:
                    headers = auth_bridge.build_browser_headers(self._cookies_path)
                    if not headers:
                        return None
                    self._auth = self._construct_auth(headers)
        return self._auth

    def _client(self, mode):
        """Return ``(client, lock)`` for ``mode`` in anon|auth|prefer_auth."""
        if mode == "auth":
            client = self._get_auth()
            if client is None:
                raise AuthRequiredError("YouTube Music sign-in required")
            return client, self._auth_lock
        if mode == "prefer_auth":
            client = self._get_auth()
            if client is not None:
                return client, self._auth_lock
            return self._get_anon(), self._anon_lock
        return self._get_anon(), self._anon_lock

    @guard
    def _invoke(self, mode, method, *args, **kwargs):
        client, lock = self._client(mode)
        with lock:
            return getattr(client, method)(*args, **kwargs)

    # -- auth management -----------------------------------------------------

    def is_authenticated(self):
        return auth_bridge.is_authenticated(self._cookies_path)

    def reload_auth(self, cookies_path=None):
        """Drop the cached auth client so the next auth call rebuilds it.

        Call after the cookie file or the enable toggle changes.
        """
        with self._build_lock:
            if cookies_path is not None:
                self._cookies_path = cookies_path
            self._auth = None

    def _like_status(self, rating):
        try:
            from ytmusicapi.models.content.enums import LikeStatus

            return LikeStatus[rating]
        except Exception:
            return rating

    # PLACEHOLDER_WRAPPERS

    # -- browsing (anonymous-capable) ----------------------------------------

    def search(self, query, filter=None, limit=20, ignore_spelling=False):
        return self._invoke(
            "prefer_auth",
            "search",
            query,
            filter=filter,
            limit=limit,
            ignore_spelling=ignore_spelling,
        )

    def get_search_suggestions(self, query, detailed_runs=False):
        return self._invoke(
            "prefer_auth", "get_search_suggestions", query, detailed_runs=detailed_runs
        )

    def remove_search_suggestions(self, suggestions, indices=None):
        return self._invoke(
            "auth", "remove_search_suggestions", suggestions, indices=indices
        )

    def get_album(self, browse_id):
        return self._invoke("prefer_auth", "get_album", browse_id)

    def get_album_browse_id(self, audio_playlist_id):
        return self._invoke("prefer_auth", "get_album_browse_id", audio_playlist_id)

    def get_artist(self, channel_id):
        return self._invoke("prefer_auth", "get_artist", channel_id)

    def get_artist_albums(self, channel_id, params, limit=100, order=None):
        return self._invoke(
            "prefer_auth",
            "get_artist_albums",
            channel_id,
            params,
            limit=limit,
            order=order,
        )

    def get_song(self, video_id):
        return self._invoke("prefer_auth", "get_song", video_id)

    def get_song_related(self, browse_id):
        return self._invoke("prefer_auth", "get_song_related", browse_id)

    def get_watch_playlist(
        self, video_id=None, playlist_id=None, limit=25, radio=False, shuffle=False
    ):
        return self._invoke(
            "prefer_auth",
            "get_watch_playlist",
            videoId=video_id,
            playlistId=playlist_id,
            limit=limit,
            radio=radio,
            shuffle=shuffle,
        )

    def get_lyrics(self, browse_id, timestamps=False):
        return self._invoke(
            "prefer_auth", "get_lyrics", browse_id, timestamps=timestamps
        )

    def get_mood_categories(self):
        return self._invoke("prefer_auth", "get_mood_categories")

    def get_mood_playlists(self, params):
        return self._invoke("prefer_auth", "get_mood_playlists", params)

    def get_charts(self, country="ZZ"):
        return self._invoke("prefer_auth", "get_charts", country=country)

    def get_playlist(self, playlist_id, limit=100, related=False, suggestions_limit=0):
        return self._invoke(
            "prefer_auth",
            "get_playlist",
            playlist_id,
            limit=limit,
            related=related,
            suggestions_limit=suggestions_limit,
        )

    # PLACEHOLDER_AUTH_WRAPPERS

    # -- personalised reads (auth required) ----------------------------------

    def get_home(self, limit=3):
        return self._invoke("auth", "get_home", limit=limit)

    def get_account_info(self):
        return self._invoke("auth", "get_account_info")

    def get_library_playlists(self, limit=25):
        return self._invoke("auth", "get_library_playlists", limit=limit)

    def get_library_songs(self, limit=25, order=None):
        return self._invoke("auth", "get_library_songs", limit=limit, order=order)

    def get_library_albums(self, limit=25, order=None):
        return self._invoke("auth", "get_library_albums", limit=limit, order=order)

    def get_library_artists(self, limit=25, order=None):
        return self._invoke("auth", "get_library_artists", limit=limit, order=order)

    def get_library_subscriptions(self, limit=25, order=None):
        return self._invoke(
            "auth", "get_library_subscriptions", limit=limit, order=order
        )

    def get_liked_songs(self, limit=100):
        return self._invoke("auth", "get_liked_songs", limit=limit)

    def get_history(self):
        return self._invoke("auth", "get_history")

    # -- writes: non-destructive (no confirmation needed) --------------------

    def add_history_item(self, song):
        return self._invoke("auth", "add_history_item", song)

    def rate_song(self, video_id, rating="LIKE"):
        return self._invoke("auth", "rate_song", video_id, self._like_status(rating))

    def edit_song_library_status(self, feedback_tokens):
        return self._invoke(
            "auth", "edit_song_library_status", feedbackTokens=feedback_tokens
        )

    def subscribe_artists(self, channel_ids):
        return self._invoke("auth", "subscribe_artists", channel_ids)

    def create_playlist(
        self,
        title,
        description="",
        privacy_status="PRIVATE",
        video_ids=None,
        source_playlist=None,
    ):
        return self._invoke(
            "auth",
            "create_playlist",
            title,
            description,
            privacy_status=privacy_status,
            video_ids=video_ids,
            source_playlist=source_playlist,
        )

    def add_playlist_items(
        self, playlist_id, video_ids=None, source_playlist=None, duplicates=False
    ):
        return self._invoke(
            "auth",
            "add_playlist_items",
            playlist_id,
            videoIds=video_ids,
            source_playlist=source_playlist,
            duplicates=duplicates,
        )

    # -- writes: destructive (UI must confirm before calling) ----------------

    def rate_playlist(self, playlist_id, rating="INDIFFERENT"):
        return self._invoke(
            "auth", "rate_playlist", playlist_id, self._like_status(rating)
        )

    def unsubscribe_artists(self, channel_ids):
        return self._invoke("auth", "unsubscribe_artists", channel_ids)

    def edit_playlist(self, playlist_id, **kwargs):
        return self._invoke("auth", "edit_playlist", playlist_id, **kwargs)

    def delete_playlist(self, playlist_id):
        return self._invoke("auth", "delete_playlist", playlist_id)

    def remove_playlist_items(self, playlist_id, videos):
        return self._invoke("auth", "remove_playlist_items", playlist_id, videos)

    def remove_history_items(self, feedback_tokens):
        return self._invoke("auth", "remove_history_items", feedback_tokens)

    # PLACEHOLDER_DEFERRED

    # -- deferred from UI: uploads (service wrappers present) -----------------

    def get_library_upload_songs(self, limit=25, order=None):
        return self._invoke(
            "auth", "get_library_upload_songs", limit=limit, order=order
        )

    def get_library_upload_albums(self, limit=25, order=None):
        return self._invoke(
            "auth", "get_library_upload_albums", limit=limit, order=order
        )

    def get_library_upload_artists(self, limit=25, order=None):
        return self._invoke(
            "auth", "get_library_upload_artists", limit=limit, order=order
        )

    def get_library_upload_album(self, browse_id):
        return self._invoke("auth", "get_library_upload_album", browse_id)

    def get_library_upload_artist(self, browse_id, limit=25):
        return self._invoke("auth", "get_library_upload_artist", browse_id, limit=limit)

    def upload_song(self, filepath):
        return self._invoke("auth", "upload_song", filepath)

    def delete_upload_entity(self, entity_id):
        return self._invoke("auth", "delete_upload_entity", entity_id)

    # -- deferred from UI: podcasts & episodes --------------------------------

    def get_library_podcasts(self, limit=25, order=None):
        return self._invoke("auth", "get_library_podcasts", limit=limit, order=order)

    def get_podcast(self, playlist_id, limit=100):
        return self._invoke("prefer_auth", "get_podcast", playlist_id, limit=limit)

    def get_episode(self, video_id):
        return self._invoke("prefer_auth", "get_episode", video_id)

    def get_channel_episodes(self, channel_id, params):
        return self._invoke("prefer_auth", "get_channel_episodes", channel_id, params)

    def get_saved_episodes(self, limit=100):
        return self._invoke("auth", "get_saved_episodes", limit=limit)


# -- process-wide singleton --------------------------------------------------

_service_instance = None
_service_lock = threading.Lock()


def get_service(refresh=False):
    """Return the shared :class:`YTMusicService`, building it on first use."""
    global _service_instance
    with _service_lock:
        if _service_instance is None or refresh:
            _service_instance = YTMusicService(
                language=_resolve_language(),
                location="",
                cookies_path=_resolve_cookies_path(),
            )
        return _service_instance


def reload_auth(cookies_path=None):
    """Convenience: rebuild the shared service's auth client after a change."""
    service = get_service()
    service.reload_auth(
        cookies_path=cookies_path
        if cookies_path is not None
        else _resolve_cookies_path()
    )
    return service
