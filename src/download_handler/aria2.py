"""Install aria2c on demand and adapt its progress to yt-dlp's hooks."""

import hashlib
import io
import logging
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from threading import Lock, Thread

import requests

import paths
from language_handler import _

logger = logging.getLogger(__name__)
_INSTALL_LOCK = Lock()
_RELEASE = "1.37.0"
_ARCHIVES = {
    32: "35f6514cc5dd7e98a87b3c4c2d25a0754b9b063dbe59bc0f22d483464f61e5b6",
    64: "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288",
}
_MAX_ARCHIVE_SIZE = 4 * 1024 * 1024
_PROGRESS = re.compile(r"\[#\w+\s+(\d+)B?/(\d+)B?.*?\bDL:(\d+)B?")
PART_SUFFIX = ".aria2.part"
PART_SUFFIXES = (PART_SUFFIX, f"{PART_SUFFIX}.aria2")


def _get_executable(check_cancelled, announce):
    if sys.platform != "win32":
        return shutil.which("aria2c")

    bits = 64 if sys.maxsize > 2**32 else 32
    directory = Path(paths.settings_path) / "aria2" / f"{_RELEASE}-{bits}"
    executable = directory / "aria2c.exe"

    while not _INSTALL_LOCK.acquire(timeout=0.2):
        check_cancelled()
    try:
        check_cancelled()
        if executable.is_file():
            return str(executable)

        announce(_("Setting up aria2c for faster downloads."))
        asset = f"aria2-{_RELEASE}-win-{bits}bit-build1"
        url = f"https://github.com/aria2/aria2/releases/download/release-{_RELEASE}/{asset}.zip"
        contents = io.BytesIO()
        with requests.get(url, stream=True, timeout=(5, 5)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=65536):
                check_cancelled()
                contents.write(chunk)
                if contents.tell() > _MAX_ARCHIVE_SIZE:
                    raise ValueError("Unexpected aria2 archive size")

        if hashlib.sha256(contents.getbuffer()).hexdigest() != _ARCHIVES[bits]:
            raise ValueError("aria2 archive checksum mismatch")

        directory.mkdir(parents=True, exist_ok=True)
        with (
            zipfile.ZipFile(contents) as archive,
            TemporaryDirectory(dir=directory) as temporary,
        ):
            staged = Path(temporary) / executable.name
            with (
                archive.open(f"{asset}/aria2c.exe") as source,
                staged.open("wb") as dest,
            ):
                shutil.copyfileobj(source, dest)
            check_cancelled()
            try:
                staged.replace(executable)
            except PermissionError:
                # A separate app instance may already be running the same binary.
                if not executable.is_file():
                    raise
        return str(executable)
    finally:
        _INSTALL_LOCK.release()


class _TransferFailed(Exception):
    pass


def _read_progress(stream, updates):
    for line in stream:
        match = _PROGRESS.search(line)
        if match:
            updates.put(tuple(map(int, match.groups())))


def downloader_class(base, check_cancelled, announce):
    # Import after HexPlayer's dynamic yt-dlp loader has selected its runtime.
    from yt_dlp.downloader.external import Aria2cFD as YtDlpAria2cFD
    from yt_dlp.utils import determine_protocol

    class Aria2cFD(YtDlpAria2cFD):
        def temp_name(self, filename):
            # A native HTTP retry must never resume a sparse aria2 partial file.
            return f"{filename}{PART_SUFFIX}"

        def _call_process(self, cmd, info_dict):
            check_cancelled()
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                raise _TransferFailed("Could not start aria2c") from exc

            updates = Queue()
            reader = Thread(
                target=_read_progress, args=(process.stdout, updates), daemon=True
            )
            reader.start()
            started = time.monotonic()
            try:
                while (
                    process.poll() is None or reader.is_alive() or not updates.empty()
                ):
                    check_cancelled()
                    try:
                        downloaded, total, speed = updates.get(timeout=0.2)
                    except Empty:
                        continue
                    self._hook_progress(
                        {
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total or None,
                            "speed": speed,
                            "eta": max(0, (total - downloaded) // speed)
                            if total and speed
                            else None,
                            "elapsed": time.monotonic() - started,
                        },
                        info_dict,
                    )
                if process.returncode:
                    raise _TransferFailed(
                        f"aria2c exited with status {process.returncode}"
                    )
                return None, None, 0
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                reader.join()
                process.stdout.close()

    class Aria2YoutubeDL(base):
        _aria2_executable = None
        _aria2_attempted = False

        def dl(self, name, info, subtitle=False, test=False):
            if (
                test
                or subtitle
                or name == "-"
                or not info.get("url")
                or info.get("impersonate") is not None
                or info.get("fragments")
                or info.get("is_live")
                or info.get("section_start")
                or info.get("section_end")
                or determine_protocol(info) not in ("http", "https")
            ):
                return super().dl(name, info, subtitle, test)

            check_cancelled()
            if not self._aria2_attempted:
                self._aria2_attempted = True
                try:
                    self._aria2_executable = _get_executable(check_cancelled, announce)
                except (
                    OSError,
                    requests.RequestException,
                    ValueError,
                    zipfile.BadZipFile,
                    KeyError,
                ) as exc:
                    logger.warning("aria2c setup failed: %s", exc)
                if not self._aria2_executable:
                    announce(
                        _(
                            "aria2c is unavailable. Continuing with the built-in downloader."
                        )
                    )

            if self._aria2_executable:
                params = {
                    **self.params,
                    "noprogress": False,
                    "external_downloader_args": {
                        "aria2c": [
                            "--enable-color=false",
                            "--human-readable=false",
                            "--truncate-console-readout=false",
                        ],
                    },
                }
                downloader = Aria2cFD(self, params)
                downloader.exe = self._aria2_executable
                for hook in self._progress_hooks:
                    downloader.add_progress_hook(hook)
                download_info = self._copy_infodict(info)
                if download_info.get("http_headers") is None:
                    download_info["http_headers"] = self._calc_headers(download_info)
                try:
                    return downloader.download(name, download_info, subtitle)
                except _TransferFailed as exc:
                    logger.warning("%s; retrying with yt-dlp", exc)
                    self._aria2_executable = None
                    for suffix in PART_SUFFIXES:
                        downloader.try_remove(f"{name}{suffix}")
                    announce(
                        _(
                            "aria2c could not complete the download. Continuing with the built-in downloader."
                        )
                    )

            return super().dl(name, info, subtitle, test)

    return Aria2YoutubeDL
