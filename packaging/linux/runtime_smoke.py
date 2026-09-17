import sys

if sys.platform == "linux" and "--packaging-smoke-test" in sys.argv:
    import ctypes
    import ctypes.util
    import importlib

    import wx

    for module in ("secretstorage", "jeepney", "fcntl", "pwd", "grp", "termios"):
        importlib.import_module(module)

    library = ctypes.util.find_library("mpv")
    if not library:
        raise RuntimeError("System libmpv was not found")
    mpv = ctypes.CDLL(library)
    mpv.mpv_create.restype = ctypes.c_void_p
    mpv.mpv_initialize.argtypes = [ctypes.c_void_p]
    mpv.mpv_initialize.restype = ctypes.c_int
    mpv.mpv_set_option_string.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    mpv.mpv_set_option_string.restype = ctypes.c_int
    mpv.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
    mpv.mpv_terminate_destroy.restype = None
    handle = mpv.mpv_create()
    if not handle:
        raise RuntimeError("mpv_create failed")
    try:
        for option, value in ((b"vo", b"null"), (b"ao", b"null"), (b"config", b"no")):
            if mpv.mpv_set_option_string(handle, option, value) < 0:
                raise RuntimeError("libmpv smoke-test option failed")
        if mpv.mpv_initialize(handle) < 0:
            raise RuntimeError("mpv_initialize failed")
        app = wx.App(False)
        frame = wx.Frame(None, title="HexPlayer")
        frame.Show()
        wx.CallLater(250, frame.Close)
        app.MainLoop()
        print(
            "Frozen GTK startup, Linux dependency imports and libmpv initialization passed"
        )
    finally:
        mpv.mpv_terminate_destroy(handle)
    raise SystemExit(0)
