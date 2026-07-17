import os

import pytest

import download_handler.downloader as downloader_module
import paths
import utils
from download_handler.downloader import DownloadCancelled, Downloader


def test_progress_hook_handles_missing_status():
    downloader = Downloader("url", ".", "best", None, None)
    downloader._progress_hook({})


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
    assert calls["opts"]["outtmpl"] == os.path.join(
        output_path, "%(title)s.%(ext)s"
    )
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
