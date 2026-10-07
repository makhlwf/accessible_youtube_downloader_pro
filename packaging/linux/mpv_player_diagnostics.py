#!/usr/bin/env python3
"""Linux libmpv playback diagnostics for HexPlayer.

Investigation harness for the "videos won't play on Linux" reports. It runs
against the *system* libmpv (unlike Windows, which bundles its own libmpv-2.dll)
and reproduces the exact option set and video-embedding path used by
``MpvMediaPlayer`` / ``MediaGui``.

Why this exists: on wxGTK ``wx.Window.GetHandle()`` returns a ``GtkWidget*``
rather than the X11 window XID that mpv's ``wid`` option expects, so the video
output can fail on Linux while audio-only playback (``hwnd=None``) keeps working.
This script captures libmpv's own log messages so the precise failure text shows
up in CI logs.

During the investigation phase it always prints a structured report and exits 0
so audio (control) and video (repro) results are visible in a single run. Set
HEXPLAYER_DIAG_STRICT=1 to make it exit non-zero when the video path fails.
"""

from __future__ import annotations

import ctypes
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from media_player import mpv_backend

# Mirror of MpvMediaPlayer.__init__ (src/media_player/mpv_backend.py). Keep in
# sync: these are set via mpv_set_option_string *before* mpv_initialize().
APP_INIT_OPTIONS: list[tuple[str, str]] = [
    ("config", "no"),
    ("terminal", "no"),
    ("osc", "no"),
    ("osd-level", "0"),
    ("osd-on-seek", "no"),
    ("input-default-bindings", "no"),
    ("volume-max", "350"),
    ("keep-open", "no"),
    ("cache", "yes"),
]

MPV_EVENT_LOG_MESSAGE = 2


class MpvEventLogMessage(ctypes.Structure):
    _fields_ = [
        ("prefix", ctypes.c_char_p),
        ("level", ctypes.c_char_p),
        ("text", ctypes.c_char_p),
        ("log_level", ctypes.c_int),
    ]


def _decode(value: bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if value else ""


def _safe(text: str) -> str:
    """Drop characters the current stdout encoding can't represent.

    libmpv log lines contain glyphs (e.g. '●') that crash a cp1252 Windows
    console; Linux CI runs UTF-8 and is unaffected.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _configure_log_api(lib: ctypes.CDLL) -> None:
    lib.mpv_request_log_messages.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.mpv_request_log_messages.restype = ctypes.c_int


def _err(lib: ctypes.CDLL, code: int) -> str:
    text = lib.mpv_error_string(code)
    return _decode(text) if text else str(code)


def _print_header(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * 4}", flush=True)


def report_environment(lib: ctypes.CDLL) -> None:
    _print_header("ENVIRONMENT")
    print(f"sys.platform      = {sys.platform}", flush=True)
    print(f"DISPLAY           = {os.environ.get('DISPLAY', '<unset>')}", flush=True)
    print(
        f"WAYLAND_DISPLAY   = {os.environ.get('WAYLAND_DISPLAY', '<unset>')}",
        flush=True,
    )
    print(
        f"XDG_SESSION_TYPE  = {os.environ.get('XDG_SESSION_TYPE', '<unset>')}",
        flush=True,
    )
    print(
        f"GDK_BACKEND       = {os.environ.get('GDK_BACKEND', '<unset>')}",
        flush=True,
    )
    try:
        api = lib.mpv_client_api_version()
        print(
            f"libmpv API        = {api} (0x{api:08x} -> {api >> 16}.{api & 0xFFFF})",
            flush=True,
        )
    except Exception as exc:
        print(f"libmpv API        = <unavailable: {exc}>", flush=True)


def probe_options(lib: ctypes.CDLL) -> list[str]:
    """Set each app init option on a fresh handle and record what libmpv says.

    A single rejected option aborts MpvMediaPlayer.__init__ (it raises via
    _check), so this pinpoints any option this libmpv build does not accept.
    """
    _print_header("OPTION PROBE (pre-init, system libmpv)")
    rejected: list[str] = []
    handle = lib.mpv_create()
    if not handle:
        print("mpv_create failed", flush=True)
        return ["<mpv_create failed>"]
    try:
        for name, value in APP_INIT_OPTIONS:
            code = lib.mpv_set_option_string(
                handle, name.encode("utf-8"), value.encode("utf-8")
            )
            status = "ok" if code >= 0 else f"REJECTED ({_err(lib, code)})"
            if code < 0:
                rejected.append(name)
            print(f"  {name:<24} = {value:<6} -> {status}", flush=True)
    finally:
        lib.mpv_terminate_destroy(handle)
    if rejected:
        print(f"REJECTED OPTIONS: {', '.join(rejected)}", flush=True)
    else:
        print("All app init options accepted by this libmpv build.", flush=True)
    return rejected


def run_playback(
    lib: ctypes.CDLL,
    url: str,
    label: str,
    *,
    wid: int | None = None,
    extra_options: list[tuple[str, str]] | None = None,
    timeout_s: float = 12.0,
) -> bool:
    """Drive a raw libmpv handle through loadfile and report the outcome.

    Replicates MpvMediaPlayer's option set, optionally sets ``wid`` (the video
    embedding path), captures libmpv log messages, and waits for FILE_LOADED /
    END_FILE. Returns True if the file loaded and played without an error EOF.
    """
    _print_header(f"PLAYBACK: {label}")
    print(f"  url = {url}", flush=True)
    print(f"  wid = {wid!r}", flush=True)

    handle = lib.mpv_create()
    if not handle:
        print("  mpv_create failed", flush=True)
        return False

    for name, value in APP_INIT_OPTIONS:
        lib.mpv_set_option_string(handle, name.encode(), value.encode())
    for name, value in extra_options or []:
        code = lib.mpv_set_option_string(handle, name.encode(), value.encode())
        if code < 0:
            print(f"  option {name}={value} REJECTED ({_err(lib, code)})", flush=True)
    if wid is not None:
        code = lib.mpv_set_option_string(handle, b"wid", str(int(wid)).encode())
        if code < 0:
            print(f"  wid option REJECTED ({_err(lib, code)})", flush=True)

    lib.mpv_request_log_messages(handle, b"info")

    if lib.mpv_initialize(handle) < 0:
        print("  mpv_initialize failed", flush=True)
        lib.mpv_terminate_destroy(handle)
        return False

    command = (ctypes.c_char_p * 3)(b"loadfile", url.encode("utf-8"), None)
    if lib.mpv_command(handle, command) < 0:
        print("  loadfile command failed", flush=True)
        lib.mpv_terminate_destroy(handle)
        return False

    loaded = False
    ok = False
    logs: list[str] = []
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            event = lib.mpv_wait_event(handle, 0.1).contents
            if event.event_id == MPV_EVENT_LOG_MESSAGE and event.data:
                msg = ctypes.cast(
                    event.data, ctypes.POINTER(MpvEventLogMessage)
                ).contents
                line = f"[{_decode(msg.prefix)}/{_decode(msg.level)}] {_decode(msg.text)}".strip()
                logs.append(line)
            elif event.event_id == mpv_backend.MPV_EVENT_FILE_LOADED:
                loaded = True
            elif event.event_id == mpv_backend.MPV_EVENT_END_FILE and event.data:
                end = ctypes.cast(
                    event.data, ctypes.POINTER(mpv_backend.MpvEventEndFile)
                ).contents
                reason = end.reason
                if reason == mpv_backend.MPV_END_FILE_REASON_EOF:
                    ok = loaded
                    print(f"  END_FILE reason=EOF error={end.error}", flush=True)
                elif reason == mpv_backend.MPV_END_FILE_REASON_ERROR:
                    print(
                        f"  END_FILE reason=ERROR error={_err(lib, end.error)}",
                        flush=True,
                    )
                else:
                    print(f"  END_FILE reason={reason} error={end.error}", flush=True)
                break
    finally:
        for line in logs[-40:]:
            print(f"  mpv> {_safe(line)}", flush=True)
        lib.mpv_terminate_destroy(handle)

    print(f"  RESULT: loaded={loaded} played_to_eof={ok}", flush=True)
    return ok


def make_test_audio(directory: Path) -> str:
    audio = directory / "diag_tone.wav"
    sample_rate = 16000
    seconds = 1
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
        stream.writeframes(
            b"".join(
                struct.pack(
                    "<h", int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                )
                for i in range(sample_rate * seconds)
            )
        )
    return str(audio)


def make_test_video(directory: Path) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # mpv can synthesize a stream via libavdevice/lavfi as a fallback.
        return "av://lavfi:testsrc=duration=2:size=320x240:rate=15"
    video = directory / "diag_clip.mp4"
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=320x240:rate=15",
        "-pix_fmt",
        "yuv420p",
        str(video),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"ffmpeg test-clip generation failed: {exc}", flush=True)
        return "av://lavfi:testsrc=duration=2:size=320x240:rate=15"
    return str(video)


def probe_loadfile_signature(lib: ctypes.CDLL, url: str, audio_url: str) -> None:
    """Reproduce MpvMediaPlayer._load_current's node command in both shapes.

    mpv 0.38 (API 2.3) inserted an <index> arg into loadfile *before* <options>.
    HexPlayer builds the 5-arg (with-index) shape. On older system libmpv this
    is the prime suspect for the "invalid argument" playback failure: the app
    ships the new shape while the runtime expects the old one. This runs the
    exact node command both ways and reports the return code for each, so the
    CI log shows which shape the *system* libmpv actually accepts.
    """
    _print_header("LOADFILE COMMAND SIGNATURE (node command, real app path)")
    api = 0
    try:
        api = int(lib.mpv_client_api_version())
    except Exception:
        pass
    expected = api >= mpv_backend.MPV_LOADFILE_INDEX_API
    print(
        f"  runtime API = 0x{api:08x}; app will send "
        f"{'5-arg (with index)' if expected else '4-arg (legacy)'} shape",
        flush=True,
    )
    # Mirror parse_player_options output for a real YouTube DASH stream.
    options = {"user-agent": "HexPlayer/diag", "audio-file": audio_url}

    for use_index, label in (
        (True, "5-arg (index, mpv>=0.38)"),
        (False, "4-arg (legacy)"),
    ):
        handle = lib.mpv_create()
        if not handle:
            print(f"  [{label}] mpv_create failed", flush=True)
            continue
        for name, value in APP_INIT_OPTIONS:
            lib.mpv_set_option_string(handle, name.encode(), value.encode())
        lib.mpv_set_option_string(handle, b"vo", b"null")
        if lib.mpv_initialize(handle) < 0:
            print(f"  [{label}] mpv_initialize failed", flush=True)
            lib.mpv_terminate_destroy(handle)
            continue
        keepalive: list[bytes] = []
        root = _build_loadfile_node(
            url, options, use_index=use_index, keepalive=keepalive
        )
        code = lib.mpv_command_node(handle, ctypes.byref(root), None)
        status = "OK" if code >= 0 else f"ERROR ({_err(lib, code)})"
        marker = "  <-- shape HexPlayer sends" if use_index == expected else ""
        print(f"  [{label}] mpv_command_node -> {status}{marker}", flush=True)
        lib.mpv_terminate_destroy(handle)


def _build_loadfile_node(
    url: str, options: dict[str, str], *, use_index: bool, keepalive: list[bytes]
) -> mpv_backend.MpvNode:
    """Build the loadfile MPV_FORMAT_NODE_ARRAY exactly like _load_current."""
    mb = mpv_backend

    def snode(value: str) -> mpv_backend.MpvNode:
        data = value.encode("utf-8")
        keepalive.append(data)
        node = mb.MpvNode()
        node.format = mb.MPV_FORMAT_STRING
        node.u.string = ctypes.c_char_p(data)
        return node

    num_args = 5 if use_index else 4
    command_values = (mb.MpvNode * num_args)()
    command_values[0] = snode("loadfile")
    command_values[1] = snode(url)
    command_values[2] = snode("replace")
    options_index = 3
    if use_index:
        command_values[3] = snode("-1")
        options_index = 4

    option_values = (mb.MpvNode * len(options))()
    option_keys = (ctypes.c_char_p * len(options))()
    for index, (key, value) in enumerate(options.items()):
        key_bytes = key.encode("utf-8")
        keepalive.append(key_bytes)
        option_keys[index] = ctypes.c_char_p(key_bytes)
        option_values[index] = snode(value)

    option_list = mb.MpvNodeList()
    option_list.num = len(options)
    option_list.values = option_values
    option_list.keys = option_keys
    option_node = mb.MpvNode()
    option_node.format = mb.MPV_FORMAT_NODE_MAP
    option_node.u.list = ctypes.pointer(option_list)
    command_values[options_index] = option_node

    command_list = mb.MpvNodeList()
    command_list.num = num_args
    command_list.values = command_values
    command_list.keys = None
    root = mb.MpvNode()
    root.format = mb.MPV_FORMAT_NODE_ARRAY
    root.u.list = ctypes.pointer(command_list)
    # Keep every backing object alive until the command call returns.
    root._keepalive = (  # type: ignore[attr-defined]
        command_values,
        command_list,
        option_list,
        option_values,
        option_keys,
    )
    return root


def probe_gtk_handle() -> int | None:
    """Create a real wxGTK frame and return GetHandle() — the MediaGui wid path."""
    _print_header("wxGTK GetHandle() (video embedding source)")
    try:
        import wx
    except Exception as exc:
        print(f"wx import failed: {exc}", flush=True)
        return None
    try:
        app = wx.App()  # noqa: F841
        frame = wx.Frame(None, title="diag")
        frame.SetSize((320, 240))
        frame.Show()
        for _ in range(20):
            wx.Yield()
            time.sleep(0.02)
        handle = frame.GetHandle()
        print(f"  GetHandle() = {handle!r} (type {type(handle).__name__})", flush=True)
        print(
            "  NOTE: on wxGTK this is a GtkWidget*, NOT an X11 window XID; "
            "mpv 'wid' expects the XID.",
            flush=True,
        )
        return int(handle) if handle else None
    except Exception as exc:
        print(f"  frame/GetHandle failed: {exc}", flush=True)
        return None


def main() -> int:
    lib = mpv_backend._load_mpv()
    _configure_log_api(lib)
    report_environment(lib)
    probe_options(lib)

    with tempfile.TemporaryDirectory(prefix="hexplayer_diag_") as tmp:
        directory = Path(tmp)
        audio_url = make_test_audio(directory)
        video_url = make_test_video(directory)

        # Prime suspect: the loadfile command signature mismatch (mpv < 0.38).
        # This exercises the real node command path, unlike the raw 2-arg
        # loadfile used by the run_playback controls below.
        probe_loadfile_signature(lib, video_url, audio_url)

        # Control: audio-only path (MediaGui audio_mode -> hwnd=None, :no-video).
        audio_ok = run_playback(
            lib,
            audio_url,
            "audio control (no video, ao=null)",
            extra_options=[("vid", "no"), ("ao", "null")],
        )

        # Control: video decode without any window (vo=null rules out codecs).
        video_null_ok = run_playback(
            lib, video_url, "video decode (vo=null)", extra_options=[("vo", "null")]
        )

        # Control: windowed video, mpv creates its own X11 window (wid unset).
        video_windowed_ok = run_playback(lib, video_url, "video windowed (wid unset)")

        # Repro: video embedded into the wxGTK frame handle (MediaGui video path).
        handle = probe_gtk_handle()
        video_embedded_ok: bool | None = None
        if handle is not None:
            video_embedded_ok = run_playback(
                lib, video_url, "video embedded (wid = wxGTK GetHandle)", wid=handle
            )

    _print_header("SUMMARY")
    print(
        f"  audio (control)            : {'PASS' if audio_ok else 'FAIL'}", flush=True
    )
    print(
        f"  video decode (vo=null)     : {'PASS' if video_null_ok else 'FAIL'}",
        flush=True,
    )
    print(
        f"  video windowed (no wid)    : {'PASS' if video_windowed_ok else 'FAIL'}",
        flush=True,
    )
    embedded_label = (
        "SKIPPED (no handle)"
        if video_embedded_ok is None
        else ("PASS" if video_embedded_ok else "FAIL")
    )
    print(f"  video embedded (wxGTK wid) : {embedded_label}", flush=True)

    if os.environ.get("HEXPLAYER_DIAG_STRICT") == "1" and video_embedded_ok is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
