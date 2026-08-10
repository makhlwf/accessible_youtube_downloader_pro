import os

import pytest

import download_handler.downloader as downloader_module
import paths
import utils
from download_handler.downloader import (
    AUDIO_KBPS_FORMAT_MAP,
    DownloadCancelled,
    Downloader,
    _fallback_format_for_kbps,
    clean_progress_text,
    get_audio_download_format,
    get_video_download_format,
)


def test_progress_hook_handles_missing_status():
    downloader = Downloader("url", ".", "best", None, None)
    downloader._progress_hook({})


def test_clean_progress_text_strips_ansi_sequences():
    assert clean_progress_text("\x1b[0;94m 791.19KiB\x1b[0m") == "791.19KiB"
    assert clean_progress_text("[0;33m00:16[0m") == "00:16"


def test_progress_hook_raises_when_cancelled():
    downloader = Downloader(
        "url",
        ".",
        "best",
        None,
        None,
        cancel_checker=lambda: True,
    )

    with pytest.raises(DownloadCancelled):
        downloader._progress_hook({"status": "downloading"})


def test_audio_download_format_falls_back_when_converting_to_mp3():
    downloader = Downloader("url", ".", "bestaudio[ext=m4a]", None, None, convert=True)

    assert get_audio_download_format(convert=True) == "bestaudio/best"
    assert downloader._effective_format() == "bestaudio/best"


def test_audio_download_format_explicit_kbps_128():
    assert get_audio_download_format(kbps=128) == AUDIO_KBPS_FORMAT_MAP[128]


def test_video_download_format_falls_back_for_selected_quality():
    expected = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=720]+bestaudio/"
        "best[height<=720][ext=mp4]/best[height<=720]/best"
    )

    assert get_video_download_format(720) == expected


def test_base_options_use_audio_fallback_for_mp3_conversion(monkeypatch):
    monkeypatch.setattr(
        downloader_module,
        "config_get",
        lambda key: "1" if key == "conversion" else "",
    )

    downloader = Downloader("url", ".", "bestaudio[ext=m4a]", None, None, convert=True)
    options = downloader._base_options()

    assert options["format"] == "bestaudio/best"
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"


def test_download_prepares_runtime_path_and_output_directory(monkeypatch):
    calls = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            calls["opts"] = opts
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            calls["urls"] = urls
            self.opts["post_hooks"][0]({"filepath": "downloaded.mp4"})

    made_dirs = []
    ffmpeg_dir = os.path.abspath("test-ffmpeg")
    main_path = os.path.abspath("test-runtime")
    output_path = os.path.abspath("test-downloads")
    monkeypatch.setattr(paths, "ffmpeg_dir", ffmpeg_dir)
    monkeypatch.setattr(paths, "main_path", main_path)
    monkeypatch.setattr(utils, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(downloader_module, "config_get", lambda key: "")
    monkeypatch.setattr(
        downloader_module.os,
        "makedirs",
        lambda path, exist_ok=False: made_dirs.append((path, exist_ok)),
    )
    monkeypatch.setattr(downloader_module.os.path, "exists", lambda path: True)
    monkeypatch.setenv("PATH", "existing")

    downloader = Downloader(
        "https://youtube.com/watch?v=test",
        output_path,
        "best",
        None,
        None,
        folder=True,
    )

    assert downloader.download() == 0
    assert downloader.last_file == "downloaded.mp4"
    assert made_dirs == [(output_path, True)]
    assert calls["urls"] == ["https://youtube.com/watch?v=test"]
    path_parts = {
        os.path.normcase(os.path.normpath(path))
        for path in os.environ["PATH"].split(os.pathsep)
    }
    assert os.path.normcase(os.path.normpath(ffmpeg_dir)) in path_parts
    assert os.path.normcase(os.path.normpath(main_path)) in path_parts
    assert calls["opts"]["outtmpl"] == os.path.join(output_path, "%(title)s.%(ext)s")
    assert calls["opts"]["noplaylist"] is False
    assert calls["opts"]["continuedl"] is True
    assert calls["opts"]["post_hooks"]
    assert calls["opts"]["postprocessor_hooks"]


def test_cookie_fallback_retries_without_cookiefile(monkeypatch):
    option_sets = []

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            option_sets.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            if "cookiefile" in self.opts:
                raise RuntimeError("cookie database is locked")

    monkeypatch.setattr(utils, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(
        downloader_module,
        "config_get",
        lambda key: "cookies.txt" if key == "cookiespath" else "",
    )
    monkeypatch.setattr(
        downloader_module.os,
        "makedirs",
        lambda path, exist_ok=False: None,
    )
    monkeypatch.setattr(
        downloader_module.os.path,
        "exists",
        lambda path: str(path).endswith("cookies.txt"),
    )

    downloader = Downloader("url", "downloads", "best", None, None)

    assert downloader.download_with_cookie_fallback() == 0
    assert len(option_sets) == 2
    assert option_sets[0]["cookiefile"] == "cookies.txt"
    assert "cookiefile" not in option_sets[1]


def test_audio_download_format_returns_exact_match_for_known_kbps():
    for kbps, expected in AUDIO_KBPS_FORMAT_MAP.items():
        result = get_audio_download_format(kbps=kbps)
        assert result == expected, f"kbps={kbps}"


def test_audio_download_format_falls_back_for_unknown_kbps():
    result = get_audio_download_format(kbps=80)
    assert result == AUDIO_KBPS_FORMAT_MAP[96]


def test_audio_download_format_falls_back_below_for_unknown_kbps():
    result = get_audio_download_format(kbps=100)
    assert result == AUDIO_KBPS_FORMAT_MAP[96]


def test_audio_download_format_falls_back_to_nearest_lower():
    result = get_audio_download_format(kbps=160)
    assert result == AUDIO_KBPS_FORMAT_MAP[128]


def test_audio_download_format_falls_back_to_lowest_for_very_small_kbps():
    result = get_audio_download_format(kbps=1)
    assert result == AUDIO_KBPS_FORMAT_MAP[96]


def test_audio_download_format_ignores_kbps_when_convert_true():
    result = get_audio_download_format(convert=True, kbps=128)
    assert result == "bestaudio/best"


def test_audio_download_format_defaults_to_96_when_no_config():
    result = get_audio_download_format()
    assert result == AUDIO_KBPS_FORMAT_MAP[96]


def test_fallback_format_for_kbps_returns_nearest_lower():
    assert _fallback_format_for_kbps(128) == AUDIO_KBPS_FORMAT_MAP[128]
    assert _fallback_format_for_kbps(200) == AUDIO_KBPS_FORMAT_MAP[192]
    assert _fallback_format_for_kbps(400) == AUDIO_KBPS_FORMAT_MAP[320]


def test_effective_format_passes_kbps_to_audio():
    downloader = Downloader("url", ".", "bestaudio[ext=m4a]", None, None, kbps=320)
    assert downloader._effective_format() == AUDIO_KBPS_FORMAT_MAP[320]


def test_effective_format_ignores_kbps_for_mp3_convert():
    downloader = Downloader(
        "url", ".", "bestaudio[ext=m4a]", None, None, convert=True, kbps=128
    )
    assert downloader._effective_format() == "bestaudio/best"


def test_diagnose_extraction_error_age_verification():
    from media_player.media_gui import diagnose_extraction_error

    msg = diagnose_extraction_error("Sign in to confirm your age")
    assert "تسجيل الدخول" in msg
    assert "sign-in or age verification" in msg
    assert "\n" in msg


def test_diagnose_extraction_error_unavailable_private():
    from media_player.media_gui import diagnose_extraction_error

    msg = diagnose_extraction_error("This is a private video")
    assert "غير متاح أو خاص" in msg
    assert "unavailable or private" in msg
    assert "\n" in msg


def test_diagnose_extraction_error_generic():
    from media_player.media_gui import diagnose_extraction_error

    msg = diagnose_extraction_error("Unknown player error")
    assert "تعذر تشغيل المقطع: Unknown player error" in msg
    assert "Could not play video: Unknown player error" in msg
    assert "\n" in msg


def test_diagnose_download_error_missing_ytdlp(monkeypatch):
    from download_handler.downloader import diagnose_download_error

    monkeypatch.setattr(utils, "YoutubeDL", None)
    msg = diagnose_download_error("missing yt-dlp binary")
    assert "لم يتم العثور على مكتبة yt-dlp" in msg
    assert "yt-dlp library was not found" in msg
    assert "\n" in msg


def test_diagnose_download_error_network_timeout():
    from download_handler.downloader import diagnose_download_error

    msg = diagnose_download_error("HTTP Error 504: Gateway Timeout")
    assert "انتهت مهلة الإرسال" in msg
    assert "Network timeout" in msg
    assert "\n" in msg


def test_diagnose_download_error_permission_or_disk_full():
    from download_handler.downloader import diagnose_download_error

    msg = diagnose_download_error("Permission denied: 'C:\\downloads\\video.mp4'")
    assert "تم رفض الوصول أو القرص ممتلئ" in msg
    assert "Permission denied or disk full" in msg
    assert "\n" in msg


def test_diagnose_download_error_generic():
    from download_handler.downloader import diagnose_download_error

    msg = diagnose_download_error("Some unexpected error")
    assert "حدث خطأ أثناء التنزيل: Some unexpected error" in msg
    assert "Download error occurred: Some unexpected error" in msg
    assert "\n" in msg
