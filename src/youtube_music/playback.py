"""Open ``MediaGui`` for a YouTube Music row, reusing the YouTube stream path.

ytmusicapi gives us video ids, not streams, so playback resolves the stream via
``utils.get_playable_stream`` (the same yt-dlp path the YouTube UI uses) and
hands a :class:`~youtube_music.adapters.YTMusicResult` to ``MediaGui`` so the
player's queue, auto-advance, scraper prefetch, and download all work unchanged.
Heavy modules are imported lazily so importing this module stays cheap.
"""

import logging

logger = logging.getLogger(__name__)


def play_result(frame, result, index, audio_mode=True):
    """Resolve and play ``result[index]`` in ``MediaGui``.

    ``frame`` is the HomeScreen frame; it is hidden while the player is open and
    reshown (still on the YouTube Music panel) when the player closes. Returns
    the ``MediaGui`` instance, or ``None`` if the row is not playable or the
    stream could not be resolved.
    """
    import utils
    from gui.activity_dialog import LoadingDialog
    from language_handler import _
    from media_player.media_gui import MediaGui
    from speech_client import speak

    try:
        row = result.data_list[index]
    except IndexError, AttributeError, TypeError:
        return None
    if not row.get("videoId"):
        return None

    url = result.get_url(index)
    title = result.get_title(index)
    stream = result.get_stream(index, audio_mode=audio_mode)
    if stream is None:
        if not utils.check_yt_dlp(frame):
            return None
        stream = LoadingDialog(
            frame, _("جاري التشغيل"), utils.get_playable_stream, url, audio_mode
        ).res
    if not stream:
        utils.show_error(_("تعذر تشغيل هذا المقطع."), parent=frame)
        speak(_("تعذر التشغيل"))
        return None

    gui = MediaGui(
        frame,
        title,
        stream,
        url,
        can_download=True,
        results=result,
        audio_mode=audio_mode,
    )
    frame.Hide()
    return gui


def start_radio(frame, result, index, audio_mode=True):
    """Start a radio/watch-playlist seeded from ``result[index]``.

    Fetches the watch playlist on a worker thread (via ``LoadingDialog``), builds
    a playable queue, and opens ``MediaGui`` in mix mode so it auto-advances
    through the radio. Returns the ``MediaGui`` or ``None``.
    """
    import utils
    from gui.activity_dialog import LoadingDialog
    from language_handler import _
    from media_player.media_gui import MediaGui
    from speech_client import speak

    from . import adapters
    from .service import get_service

    try:
        row = result.data_list[index]
    except IndexError, AttributeError, TypeError:
        return None
    video_id = row.get("videoId")
    playlist_id = row.get("playlistId")
    if not video_id and not playlist_id:
        return None

    def _fetch():
        service = get_service()
        data = service.get_watch_playlist(
            video_id=video_id, playlist_id=playlist_id, radio=True
        )
        return adapters.normalize_items((data or {}).get("tracks"))

    rows = LoadingDialog(frame, _("جاري بدء الراديو"), _fetch).res
    rows = [r for r in (rows or []) if r.get("videoId")]
    if not rows:
        utils.show_error(_("تعذر بدء الراديو."), parent=frame)
        speak(_("تعذر بدء الراديو"))
        return None

    radio_result = adapters.YTMusicResult(rows)
    first_url = radio_result.get_url(0)
    if not utils.check_yt_dlp(frame):
        return None
    stream = LoadingDialog(
        frame, _("جاري التشغيل"), utils.get_playable_stream, first_url, audio_mode
    ).res
    if not stream:
        utils.show_error(_("تعذر تشغيل هذا المقطع."), parent=frame)
        speak(_("تعذر التشغيل"))
        return None

    gui = MediaGui(
        frame,
        radio_result.get_title(0),
        stream,
        first_url,
        can_download=True,
        results=radio_result,
        audio_mode=audio_mode,
        mix_mode=True,
    )
    frame.Hide()
    return gui
