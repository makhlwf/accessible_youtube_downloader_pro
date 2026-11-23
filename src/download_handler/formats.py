"""Format selectors and output containers for yt-dlp downloads."""

from app_state.settings_handler import config_get

FORMAT_VIDEO_MP4 = "mp4"
FORMAT_VIDEO_MKV = "mkv"
FORMAT_AUDIO_M4A = "m4a"
FORMAT_AUDIO_MP3 = "mp3"
FORMAT_AUDIO_WAV = "wav"
FORMAT_AUDIO_FLAC = "flac"

AUDIO_KBPS_FORMAT_MAP = {
    96: (
        "bestaudio[abr=96][ext=m4a]/bestaudio[abr=96]/bestaudio[ext=m4a]/bestaudio/best"
    ),
    128: (
        "bestaudio[abr=128][ext=m4a]/bestaudio[abr=128]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
    192: (
        "bestaudio[abr=192][ext=m4a]/bestaudio[abr=192]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
    320: (
        "bestaudio[abr=320][ext=m4a]/bestaudio[abr=320]/"
        "bestaudio[ext=m4a]/bestaudio/best"
    ),
}

AUDIO_KBPS_SORTED = sorted(AUDIO_KBPS_FORMAT_MAP.keys())


def _fallback_format_for_kbps(kbps):
    for candidate in reversed(AUDIO_KBPS_SORTED):
        if candidate <= kbps:
            return AUDIO_KBPS_FORMAT_MAP[candidate]
    return AUDIO_KBPS_FORMAT_MAP[AUDIO_KBPS_SORTED[0]]


def get_audio_download_format(convert=False, kbps=None, audio_format=None):
    if convert or audio_format in ("mp3", "wav", "flac"):
        return "bestaudio/best"
    if kbps is None:
        kbps = int(config_get("conversion"))
    kbps = int(kbps)
    if kbps in AUDIO_KBPS_FORMAT_MAP:
        return AUDIO_KBPS_FORMAT_MAP[kbps]
    return _fallback_format_for_kbps(kbps)


def get_video_download_format(quality=None, container="mp4"):
    if quality:
        return (
            f"bestvideo[height<={quality}][ext={container}]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}][ext={container}]/best[height<={quality}]/best"
        )
    return f"bestvideo[ext={container}]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext={container}]/best"
