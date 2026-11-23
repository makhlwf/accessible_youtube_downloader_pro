"""Compatibility imports for HexPlayer utility functions."""

# ruff: noqa: F401 -- this module intentionally re-exports these names.

from app_runtime.dependencies import (
    YOUTUBEI_IMPORT_SPECIFIER,
    YOUTUBEI_PACKAGE,
    _deno_release_asset,
    _is_newer_version,
    _run_deno_cache,
    _write_youtubei_runtime_config,
    check_deno,
    check_pot_provider,
    check_yt_dlp,
    download_deno,
    download_youtube_service,
    download_yt_dlp,
    ensure_deno_installed,
    ensure_js_dependencies,
    get_deno_version,
    get_latest_github_release,
    get_latest_npm_package_version,
    get_pot_provider_version,
    get_youtube_service_version,
    get_youtubei_version,
    get_yt_dlp_version,
    install_youtubei_version,
    refresh_youtubei_cache,
    update_deno,
    update_pot_provider,
    update_youtube_service,
    update_youtubei,
    update_yt_dlp,
)
from app_runtime.desktop import (
    configure_py_yt_subprocess,
    copy_to_clipboard,
    ensure_focus,
    set_startup,
    show_error,
)
from app_runtime.updates import (
    RELEASES_PAGE_URL,
    check_for_updates,
)
from media_player.cache import (
    InfoCache,
)
from media_player.formats import (
    AUDIO_QUALITIES,
    AUDIO_TRACK_LANGUAGES,
    VIDEO_QUALITIES,
    VIDEO_QUALITY_DESCRIPTIONS,
    get_audio_track_languages,
    get_audio_tracks_from_formats,
    get_language_display_name,
    get_quality_description,
    is_language_match,
    pick_best_format,
    select_audio_format,
)
from media_player.text import (
    format_duration,
    sanitize_filename,
    time_formatting,
    time_to_seconds,
)
from youtube_backend import ytdlp_runtime as _ytdlp_runtime
from youtube_backend.comments import (
    get_comment_replies,
    get_video_comments,
    like_comment,
    post_video_comment,
    reply_to_comment,
)
from youtube_backend.feeds import (
    get_home_feed,
    get_shorts_feed,
    get_subscribed_channels,
    get_subscriptions_feed,
    get_watch_history,
    update_watch_history,
)
from youtube_backend.metadata import (
    get_video_chapters,
    get_video_like_info,
    get_video_likes,
    like_video,
    validate_video_reaction,
)
from youtube_backend.mixes import (
    extract_mix_id,
    extract_video_id,
    get_mix,
    is_mix_url,
    resolve_mix_seed_url,
)
from youtube_backend.network_warmup import (
    prefetch_dns,
)
from youtube_backend.playback import (
    Stream,
    get_audio_stream,
    get_available_audio_tracks,
    get_available_qualities,
    get_available_subtitles,
    get_media_info,
    get_playable_stream,
    get_specific_quality_stream,
    get_subtitle_cues,
    get_video_stream,
)
from youtube_backend.region import (
    get_windows_region,
)
from youtube_backend.session import (
    ensure_cookies_configured,
    has_cookies_file,
)
from youtube_backend.subtitles import (
    SUBTITLE_EXT_PRIORITY,
)
from youtube_backend.youtube_url_utils import (
    extract_launch_youtube_url,
    extract_supported_youtube_url,
    get_video_id,
    is_supported_youtube_url,
    youtube_regexp,
)
from youtube_backend.ytdlp_runtime import (
    AUTHED_INCOMPATIBLE_CLIENTS,
    PLAYER_OPTS,
    InvalidYtDlpArchiveError,
    YtDlpLogger,
    _warm_youtube_extractor,
    get_configured_js_runtimes,
    get_configured_player_clients,
    get_player_client_choices,
    get_ydl_instance,
    load_yt_dlp,
)

# Prime DNS once through the existing utility entry point.
prefetch_dns()


def __getattr__(name):
    if name in {"YoutubeDL", "yt_dlp_module"}:
        return getattr(_ytdlp_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
