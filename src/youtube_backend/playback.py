"""Stream extraction, playback caches, and subtitle retrieval."""

import logging
import os
import re
import threading

import requests

import paths
from app_state.settings_handler import config_get
from media_player.cache import InfoCache
from media_player.formats import (
    AUDIO_QUALITIES,
    _clamp_index,
    get_audio_tracks_from_formats,
    pick_best_format,
)
from youtube_backend import ytdlp_runtime
from youtube_backend.deno_service import deno_service
from youtube_backend.mixes import resolve_mix_seed_url
from youtube_backend.region import get_windows_region
from youtube_backend.subtitles import _normalize_subtitle_tracks, _parse_subtitle_cues
from youtube_backend.ytdlp_runtime import (
    PLAYER_OPTS,
    get_configured_player_clients,
    get_ydl_instance,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


_info_cache = InfoCache(maxsize=256, default_ttl=3600)
_stream_cache = InfoCache(maxsize=256, default_ttl=1200)


_subtitle_cues_cache = InfoCache(maxsize=128, default_ttl=3600)
_stream_inflight = {}
_stream_inflight_lock = threading.Lock()


def get_available_audio_tracks(url, audio_mode=False):
    info = get_media_info(url)
    if not info:
        return []
    formats = info.get("formats", [])
    tracks = get_audio_tracks_from_formats(formats, entry=info)
    if not tracks:
        return []

    try:
        preferred_audio_idx = int(config_get("defaultaudioquality"))
    except Exception:
        preferred_audio_idx = 1
    target_abr = AUDIO_QUALITIES[
        _clamp_index(preferred_audio_idx, len(AUDIO_QUALITIES), 1)
    ]

    for track in tracks:
        fmts = track["formats"]
        fmts = [fmt for fmt in fmts if fmt.get("vcodec") == "none"] or fmts
        fmts_with_abr = [f for f in fmts if f.get("abr") is not None]
        if fmts_with_abr:
            best_fmt = min(
                fmts_with_abr, key=lambda x: abs((x.get("abr") or 0) - target_abr)
            )
        else:
            best_fmt = fmts[-1]
        track["url"] = best_fmt.get("url")
        track["format_id"] = best_fmt.get("format_id")
        track["abr"] = best_fmt.get("abr")

    return tracks


class Stream:
    def __init__(
        self,
        title,
        url,
        headers=None,
        audio_url=None,
        quality=None,
        webpage_url="",
        channel_name="",
        channel_url="",
        view_count=None,
        upload_date="",
        sponsorblock_segments=None,
        audio_track_id=None,
        audio_track_lang=None,
        audio_track_label=None,
    ):
        self.title = title
        self.url = url
        self.headers = headers or {}
        self.audio_url = audio_url
        self.quality = quality
        self.webpage_url = webpage_url
        self.channel_name = channel_name
        self.channel_url = channel_url
        self.view_count = view_count
        self.upload_date = upload_date
        self.sponsorblock_segments = sponsorblock_segments
        self.audio_track_id = audio_track_id
        self.audio_track_lang = audio_track_lang
        self.audio_track_label = audio_track_label


def _stream_from_info(
    entry,
    audio_mode=False,
    preferred_audio_lang=None,
    force_original=None,
    audio_track_id=None,
):
    formats = entry.get("formats", [])
    if audio_mode:
        preferred_audio = int(config_get("defaultaudioquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats,
            preferred_audio,
            is_video=False,
            preferred_audio_lang=preferred_audio_lang,
            force_original=force_original,
            audio_track_id=audio_track_id,
        )
    else:
        preferred_video = int(config_get("defaultvideoquality"))
        fmt, audio_fmt, quality = pick_best_format(
            formats,
            preferred_video,
            is_video=True,
            preferred_audio_lang=preferred_audio_lang,
            force_original=force_original,
            audio_track_id=audio_track_id,
        )

    if not fmt:
        fmt = entry

    title = entry.get("title")
    url_to_play = fmt.get("url")
    if not url_to_play:
        return None

    headers = {}
    headers.update(entry.get("http_headers", {}) or {})
    headers.update(fmt.get("http_headers", {}) or {})
    headers.setdefault("User-Agent", "libmpv")

    audio_url = audio_fmt.get("url") if audio_fmt else None
    track_info = (
        (audio_fmt.get("_chosen_track") if isinstance(audio_fmt, dict) else None)
        or (fmt.get("_chosen_track") if isinstance(fmt, dict) else None)
        or {}
    )
    return Stream(
        title,
        url_to_play,
        headers,
        audio_url,
        quality=quality,
        webpage_url=entry.get("webpage_url") or entry.get("original_url") or "",
        channel_name=entry.get("channel") or entry.get("uploader") or "",
        channel_url=entry.get("channel_url") or entry.get("uploader_url") or "",
        view_count=entry.get("view_count"),
        upload_date=entry.get("upload_date") or entry.get("timestamp") or "",
        audio_track_id=track_info.get("id"),
        audio_track_lang=track_info.get("lang"),
        audio_track_label=track_info.get("label"),
    )


def _begin_stream_extraction(cache_key):
    with _stream_inflight_lock:
        event = _stream_inflight.get(cache_key)
        if event is not None:
            return event, False
        event = threading.Event()
        _stream_inflight[cache_key] = event
        return event, True


def _finish_stream_extraction(cache_key, event):
    with _stream_inflight_lock:
        if _stream_inflight.get(cache_key) is event:
            del _stream_inflight[cache_key]
        event.set()


def _playback_stream_key(url, audio_mode):
    return (
        url,
        audio_mode,
        bool(config_get("force_original_audio")),
        config_get("preferred_audio_language"),
    )


def get_playable_stream(url, audio_mode=False):
    # A mix id sitting in the video slot must become the mix's first track
    # before any extraction, or yt-dlp truncates it and fails "unavailable".
    url = resolve_mix_seed_url(url)
    if "youtube.com" not in url and "youtu.be" not in url:
        url_full = f"https://www.youtube.com/watch?v={url}"
    else:
        url_full = url

    cache_key = _playback_stream_key(url_full, audio_mode)
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached

    cached_info = _info_cache.get(url_full, ttl=1200)
    if cached_info:
        stream = _stream_from_info(cached_info, audio_mode=audio_mode)
        if stream:
            _stream_cache.set(cache_key, stream)
            return stream

    # Handle finite Playlist URLs via deno service. Mix (RD...) ids are already
    # resolved to a concrete track by resolve_mix_seed_url() above, so anything
    # left here with an RD id has a real seed video to play — skip it.
    playlist_id = None
    if "list=" in url_full:
        playlist_id_match = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url_full)
        if playlist_id_match:
            playlist_id = playlist_id_match.group(1)

    logger.info(
        f"DEBUG: Checking for playlist_id. URL: {url_full}. Detected ID: {playlist_id}"
    )

    if playlist_id and not playlist_id.startswith("RD"):
        cookies_path = config_get("cookiespath")
        result = deno_service.send_command(
            "get_playlist",
            {
                "playlistId": playlist_id,
                "cookiesPath": cookies_path,
                "location": get_windows_region(),
            },
        )
        if isinstance(result, dict) and "videos" in result and result["videos"]:
            # Pick the first video to play
            first_video = result["videos"][0]
            url_full = first_video["url"]
            # We don't cache playlist extraction, but we can cache the stream of the first video
            return get_playable_stream(url_full, audio_mode=audio_mode)

    if not ytdlp_runtime.YoutubeDL:
        logger.error("yt-dlp is not installed")
        if audio_mode:
            return get_audio_stream(url_full)
        return get_video_stream(url_full)

    if paths.main_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = paths.main_path + os.pathsep + os.environ.get("PATH", "")

    url = url_full
    event, owner = _begin_stream_extraction(url_full)
    if not owner:
        event.wait(timeout=30)
        cached = _stream_cache.get(cache_key, ttl=1200)
        if cached:
            return cached
        cached_info = _info_cache.get(url_full, ttl=1200)
        if cached_info:
            stream = _stream_from_info(cached_info, audio_mode=audio_mode)
            if stream:
                _stream_cache.set(cache_key, stream)
                return stream
        return None

    logger.info(f"Extracting URL: {url}")
    cookies_path = config_get("cookiespath")

    def _extract_task(client):
        try:
            with get_ydl_instance(client, cookies_path) as ydl:
                try:
                    entry = ydl.extract_info(url, download=False)
                except Exception as e:
                    if "format" in str(e).lower():
                        retry_opts = PLAYER_OPTS.copy()
                        retry_opts.update(
                            {
                                "extractor_args": {
                                    "youtube": {
                                        "player_client": ["default"],
                                        "js_variant": "main",
                                    }
                                },
                                "js_runtimes": {"deno": {}},
                                "socket_timeout": 5,
                            }
                        )
                        if cookies_path and os.path.exists(cookies_path):
                            retry_opts["cookiefile"] = cookies_path
                        with ytdlp_runtime.YoutubeDL(retry_opts) as ydl_retry:
                            entry = ydl_retry.extract_info(url, download=False)
                    else:
                        raise

            _info_cache.set(url, entry)
            return _stream_from_info(entry, audio_mode=audio_mode)
        except Exception:
            logger.exception("Extraction failed for client %s", client)
            return None

    try:
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))
        clients = get_configured_player_clients(has_cookies=has_cookies)
        result = _extract_task(clients)
        if not result and clients != ["default"]:
            logger.warning(
                "Extraction failed with client %s, retrying with 'default' client",
                clients,
            )
            result = _extract_task(["default"])

        if result:
            _stream_cache.set(cache_key, result)
            return result

        logger.error(f"Extraction failed for {url}")
        return None
    finally:
        _finish_stream_extraction(url_full, event)


def get_media_info(url):
    # Resolve a mix id in the video slot to a real track before extraction.
    url = resolve_mix_seed_url(url)
    cached = _info_cache.get(url, ttl=3600)
    if cached:
        return cached

    if not ytdlp_runtime.YoutubeDL:
        return None

    # Opening a player starts several optional metadata lookups for this URL.
    # Share their extraction instead of creating one yt-dlp session per lookup.
    request_key = ("metadata", url)
    event, owner = _begin_stream_extraction(request_key)
    if not owner:
        event.wait(timeout=30)
        return _info_cache.get(url, ttl=3600)

    try:
        cached = _info_cache.get(url, ttl=3600)
        if cached:
            return cached
        cookies_path = config_get("cookiespath")
        has_cookies = bool(cookies_path and os.path.exists(cookies_path))

        def _extract_info_task(client):
            try:
                with get_ydl_instance(client, cookies_path) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception:
                logger.exception(
                    "get_media_info extraction failed for client %s", client
                )
                return None

        clients = get_configured_player_clients(has_cookies=has_cookies)
        info = _extract_info_task(clients)
        if not info and clients != ["default"]:
            logger.warning(
                "get_media_info failed for client %s; retrying with 'default' client",
                clients,
            )
            info = _extract_info_task(["default"])

        if info:
            _info_cache.set(url, info)
            return info

        logger.error(f"get_media_info failed for {url}")
        return None
    finally:
        _finish_stream_extraction(request_key, event)


def get_audio_stream(url):
    cache_key = _playback_stream_key(url, True)
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached
    info = get_media_info(url)
    if info is None:
        return None
    stream = _stream_from_info(info, audio_mode=True)
    if stream:
        _stream_cache.set(cache_key, stream)
    return stream


def get_video_stream(url):
    cache_key = _playback_stream_key(url, False)
    cached = _stream_cache.get(cache_key, ttl=1200)
    if cached:
        return cached
    info = get_media_info(url)
    if info is None:
        return None
    stream = _stream_from_info(info, audio_mode=False)
    if stream:
        _stream_cache.set(cache_key, stream)
    return stream


def get_available_qualities(url, audio_mode=False):
    info = get_media_info(url)
    if info is None:
        return []
    formats = info.get("formats", [])
    if not audio_mode:
        available = [
            f.get("height")
            for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]
    else:
        available = [
            f.get("abr")
            for f in formats
            if f.get("acodec") != "none"
            and f.get("vcodec") == "none"
            and f.get("abr") is not None
        ]
    return sorted(set(available))


def get_available_subtitles(url):
    info = get_media_info(url)
    return _normalize_subtitle_tracks(info)


def get_subtitle_cues(url, language_code):
    info = get_media_info(url)
    tracks = _normalize_subtitle_tracks(info)
    track = next(
        (track for track in tracks if track["code"] == language_code),
        None,
    )
    if not track:
        return []

    track_url = track.get("url")
    if track_url:
        cached = _subtitle_cues_cache.get(track_url)
        if cached is not None:
            return cached

    try:
        response = requests.get(track["url"], timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(
            "Failed to download subtitles for %s language=%s: %s",
            url,
            language_code,
            e,
        )
        return []

    cues = _parse_subtitle_cues(response.text, track.get("ext"))
    if cues and track_url:
        _subtitle_cues_cache.set(track_url, cues)
    return cues


def get_specific_quality_stream(url, height, audio_mode=False, audio_track_id=None):
    info = get_media_info(url)
    if info is None:
        return None
    title = info.get("title")
    formats = info.get("formats", [])
    stream, audio_stream, quality = pick_best_format(
        formats,
        0,
        is_video=not audio_mode,
        target_height=height if not audio_mode else None,
        audio_track_id=audio_track_id,
    )
    if audio_mode and stream is not None and isinstance(height, (int, float)):
        track = stream.get("_chosen_track")
        if track:
            selected = [
                fmt
                for fmt in track["formats"]
                if fmt.get("abr") is not None
                and (fmt.get("vcodec") == "none") == (stream.get("vcodec") == "none")
            ]
            if selected:
                stream = min(selected, key=lambda fmt: abs(fmt["abr"] - height))
                stream = {**stream, "_chosen_track": track}
                quality = stream["abr"]

    if stream:
        audio_url = audio_stream.get("url") if audio_stream else None
        track_info = (
            (
                audio_stream.get("_chosen_track")
                if isinstance(audio_stream, dict)
                else None
            )
            or (stream.get("_chosen_track") if isinstance(stream, dict) else None)
            or {}
        )
        headers = {}
        headers.update(info.get("http_headers", {}) or {})
        headers.update(stream.get("http_headers", {}) or {})
        return Stream(
            title,
            stream["url"],
            headers=headers,
            audio_url=audio_url,
            quality=quality,
            webpage_url=info.get("webpage_url") or info.get("original_url") or "",
            channel_name=info.get("channel") or info.get("uploader") or "",
            channel_url=info.get("channel_url") or info.get("uploader_url") or "",
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date") or info.get("timestamp") or "",
            audio_track_id=track_info.get("id"),
            audio_track_lang=track_info.get("lang"),
            audio_track_label=track_info.get("label"),
        )
    return None
