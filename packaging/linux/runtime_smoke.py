import sys

if sys.platform == "linux" and "--packaging-smoke-test" in sys.argv:
    import ctypes
    import ctypes.util
    import importlib
    import math
    import struct
    import tempfile
    import time
    import wave
    from pathlib import Path

    import wx

    for module in (
        "prism",
        "secretstorage",
        "jeepney",
        "fcntl",
        "pwd",
        "grp",
        "termios",
    ):
        importlib.import_module(module)

    library = ctypes.util.find_library("mpv")
    if not library:
        raise RuntimeError("System libmpv was not found")
    mpv = ctypes.CDLL(library)

    class MpvEvent(ctypes.Structure):
        _fields_ = [
            ("event_id", ctypes.c_int),
            ("error", ctypes.c_int),
            ("reply_userdata", ctypes.c_uint64),
            ("data", ctypes.c_void_p),
        ]

    class MpvEndFile(ctypes.Structure):
        _fields_ = [("reason", ctypes.c_int), ("error", ctypes.c_int)]

    mpv.mpv_create.restype = ctypes.c_void_p
    mpv.mpv_initialize.argtypes = [ctypes.c_void_p]
    mpv.mpv_initialize.restype = ctypes.c_int
    mpv.mpv_set_option_string.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    mpv.mpv_set_option_string.restype = ctypes.c_int
    mpv.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
    mpv.mpv_command.restype = ctypes.c_int
    mpv.mpv_wait_event.argtypes = [ctypes.c_void_p, ctypes.c_double]
    mpv.mpv_wait_event.restype = ctypes.POINTER(MpvEvent)
    mpv.mpv_get_property.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    mpv.mpv_get_property.restype = ctypes.c_int
    mpv.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
    mpv.mpv_terminate_destroy.restype = None
    handle = mpv.mpv_create()
    if not handle:
        raise RuntimeError("mpv_create failed")
    try:
        for option, value in (
            (b"vo", b"null"),
            (b"ao", b"null"),
            (b"config", b"no"),
            (b"load-scripts", b"no"),
            (b"idle", b"yes"),
        ):
            if mpv.mpv_set_option_string(handle, option, value) < 0:
                raise RuntimeError(f"libmpv smoke-test option failed: {option!r}")
        if mpv.mpv_initialize(handle) < 0:
            raise RuntimeError("mpv_initialize failed")
        with tempfile.TemporaryDirectory(prefix="hexplayer audio smoke ") as directory:
            audio = Path(directory) / "offline tone.wav"
            sample_rate = 16000
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
                stream.writeframes(
                    b"".join(
                        struct.pack(
                            "<h",
                            int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate)),
                        )
                        for i in range(sample_rate)
                    )
                )
            command = (ctypes.c_char_p * 3)(
                b"loadfile", str(audio).encode("utf-8"), None
            )
            if mpv.mpv_command(handle, command) < 0:
                raise RuntimeError("libmpv could not load generated offline audio")
            loaded = False
            progressed = False
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                event = mpv.mpv_wait_event(handle, 0.05).contents
                if event.error < 0:
                    raise RuntimeError(f"libmpv event failed: {event.error}")
                if event.event_id == 8:
                    loaded = True
                if event.event_id == 7:
                    if not event.data:
                        raise RuntimeError("libmpv end-file event has no payload")
                    end = ctypes.cast(event.data, ctypes.POINTER(MpvEndFile)).contents
                    if end.reason != 0 or end.error < 0 or not loaded or not progressed:
                        raise RuntimeError(
                            "Offline audio did not play to EOF: "
                            f"reason={end.reason}, error={end.error}, "
                            f"loaded={loaded}, progressed={progressed}"
                        )
                    break
                position = ctypes.c_double()
                if (
                    mpv.mpv_get_property(handle, b"time-pos", 5, ctypes.byref(position))
                    >= 0
                ):
                    progressed |= position.value >= 0.1
            else:
                raise RuntimeError("Offline libmpv playback timed out after 15 seconds")
        app = wx.App(False)
        frame = wx.Frame(None, title="HexPlayer")
        frame.Show()
        wx.CallLater(250, frame.Close)
        app.MainLoop()
        print("HexPlayer packaging smoke passed: GTK, Prism import, offline audio EOF")
    finally:
        mpv.mpv_terminate_destroy(handle)
    raise SystemExit(0)
