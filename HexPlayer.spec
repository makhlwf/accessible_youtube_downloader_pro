# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_all

ROOT = os.path.abspath(SPECPATH)
SRC_DIR = os.path.join(ROOT, "src")

# Strip symbol tables from collected binaries on Linux. wxGTK, libpython and the
# other bundled .so files ship unstripped and carry large debug/symbol sections;
# stripping them roughly halves the uncompressed Linux payload. binutils `strip`
# is present on the Linux build runners (see packaging/linux/install-deps.sh).
# PE binaries on Windows are left untouched (the Inno Setup installer already
# compresses them with lzma2/ultra64), so this is Linux-only.
STRIP = sys.platform == "linux"


def src_item_path(item):
    return os.path.normpath(os.path.join(SRC_DIR, item))


# Native runtime binary files.
# NOTE: do NOT bundle api-ms-win-* API-set stubs here. Windows resolves those
# contracts from the OS API-set schema; shipping a real file with that name can
# only shadow the OS copy, and a wrong-architecture stub makes the 64-bit
# libmpv-2.dll fail to load one of its runtime dependencies.
#
# This is the x64 *shared* libmpv build: libmpv-2.dll dynamically links the
# FFmpeg 7.x runtime (avcodec-63 / avdevice-63 / avfilter-12 / avformat-63 /
# avutil-61 / swresample-7 / swscale-10), so all seven MUST be bundled beside
# it. Unlike the previous static build, this libmpv-2.dll does NOT import
# vulkan-1.dll, so vulkan is no longer bundled (mpv loads it lazily from the OS
# only if a vulkan GPU backend is explicitly requested).
#
# ffprobe.exe is intentionally NOT bundled: yt-dlp performs all merge/remux/
# audio-extract/metadata work with ffmpeg.exe and falls back to ffmpeg for
# stream probing when ffprobe is absent (the app never uses --check-formats).
binary_files = [
    "avcodec-63.dll",
    "avdevice-63.dll",
    "avfilter-12.dll",
    "avformat-63.dll",
    "avutil-61.dll",
    "swresample-7.dll",
    "swscale-10.dll",
    "ffmpeg.exe",
    "libmpv-2.dll",
]

if sys.platform != "win32":
    binary_files = []

binaries = []
for item in binary_files:
    source_path = src_item_path(item)
    if os.path.isfile(source_path):
        binaries.append((source_path, "."))

try:
    import prism

    prism_dir = os.path.dirname(prism.__file__)
    # Fixed: Added followlinks=False to prevent infinite symlink recursion on Linux
    for root_path, _, filenames in os.walk(prism_dir, followlinks=False):
        for filename in filenames:
            if (
                sys.platform == "win32" and filename.endswith((".pyd", ".dll"))
            ) or (
                sys.platform == "linux" and (filename.endswith(".so") or ".so." in filename)
            ):
                full_src = os.path.join(root_path, filename)
                rel_dst = os.path.relpath(root_path, os.path.dirname(prism_dir))
                binaries.append((full_src, rel_dst.replace("\\", "/")))
except ImportError:
    pass

# Data files and directories
data_to_add = [
    "deno.json",
    "deno.lock",
    "service.js",
    "update_history.js",
    "../PRIVACY_POLICY.md",
    "assets",
    "browser_extension",
    "docs",
    "eq_presets",
    "languages",
]

datas = []
for item in data_to_add:
    source_path = src_item_path(item)
    if os.path.isdir(source_path):
        datas.append((source_path, item))
    elif os.path.isfile(source_path):
        datas.append((source_path, "."))

# Hidden imports
hiddenimports = [
    "optparse",
    "getpass",
    "netrc",
    "uuid",
    "fileinput",
    "shlex",
    "argparse",
    "platform",
    "subprocess",
    "ctypes",
    "ctypes.util",
    "struct",
    "hashlib",
    "hmac",
    "secrets",
    "random",
    "base64",
    "calendar",
    "datetime",
    "time",
    "shutil",
    "tempfile",
    "glob",
    "fnmatch",
    "linecache",
    "traceback",
    "tokenize",
    "token",
    "dis",
    "inspect",
    "weakref",
    "bisect",
    "heapq",
    "collections",
    "copy",
    "pprint",
    "types",
    "functools",
    "operator",
    "contextlib",
    "typing",
    "dataclasses",
    "enum",
    "pathlib",
    "pickle",
    "shelve",
    "dbm",
    "string",
    "textwrap",
    "unicodedata",
    "codecs",
    "encodings",
    "locale",
    "json",
    "csv",
    "plistlib",
    "gzip",
    "bz2",
    "lzma",
    "zipfile",
    "tarfile",
    "zlib",
    "socket",
    "ssl",
    "select",
    "selectors",
    "asyncio",
    "signal",
    "http",
    "http.client",
    "http.server",
    "http.cookiejar",
    "http.cookies",
    "email",
    "email.utils",
    "email.message",
    "email.parser",
    "email.header",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "urllib.robotparser",
    "xml",
    "xml.etree",
    "xml.etree.ElementTree",
    "xml.sax",
    "xml.dom",
    "html",
    "html.parser",
    "html.entities",
    "cgi",
    "mimetypes",
    "webbrowser",
    "threading",
    "multiprocessing",
    "queue",
    "concurrent",
    "concurrent.futures",
    "logging",
    "logging.handlers",
    "sqlite3",
    "math",
    "cmath",
    "numbers",
    "decimal",
    "fractions",
    "statistics",
    "colorsys",
    "pty",
    "tty",
    "difflib",
    "doctest",
    "pydoc",
    "_cffi_backend",
]

if sys.platform == "linux":
    hiddenimports += ["fcntl", "pwd", "grp", "termios", "pty", "tty"]
    hiddenimports += collect_submodules("secretstorage")
    hiddenimports += collect_submodules("jeepney")

for sub in ["xml", "http", "email", "urllib", "html", "encodings", "logging", "ctypes"]:
    hiddenimports += collect_submodules(sub)

try:
    import curses
    hiddenimports += collect_submodules("curses")
except ImportError:
    pass

try:
    ret_prism = collect_all("prism")
    datas += ret_prism[0]
    binaries += ret_prism[1]
    hiddenimports += ret_prism[2]
except Exception:
    pass

try:
    ret_cffi = collect_all("cffi")
    datas += ret_cffi[0]
    binaries += ret_cffi[1]
    hiddenimports += ret_cffi[2]
except Exception:
    pass

try:
    ret_sb = collect_all("sponsorblock")
    datas += ret_sb[0]
    binaries += ret_sb[1]
    hiddenimports += ret_sb[2]
except Exception:
    pass

# Analysis and EXE for HexPlayer (GUI)
a_main = Analysis(
    [os.path.join(SRC_DIR, "accessible_youtube_downloader_pro.py")],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(ROOT, "packaging", "linux", "runtime_smoke.py")]
    if sys.platform == "linux"
    else [],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Fixed: Removed exclude_system_libraries calls which cause hangs during Linux binary inspection
pyz_main = PYZ(a_main.pure)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    [],
    exclude_binaries=True,
    name="HexPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Analysis and EXE for HexPlayerNativeHost (Console, shares runtime with HexPlayer)
a_host = Analysis(
    [os.path.join(SRC_DIR, "native_messaging_host.py")],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("secretstorage") + collect_submodules("jeepney")
    if sys.platform == "linux"
    else [],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz_host = PYZ(a_host.pure)

exe_host = EXE(
    pyz_host,
    a_host.scripts,
    [],
    exclude_binaries=True,
    name="HexPlayerNativeHost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Analysis and EXE for the hexplayer CLI (Console, shares runtime with HexPlayer).
# NOTE: the CLI binary MUST NOT be named "hexplayer" — on case-insensitive
# filesystems (Windows) that collides with the "HexPlayer" GUI exe in the shared
# COLLECT directory and, since this EXE is bundled after exe_main, the console
# CLI silently overwrites HexPlayer.exe, so double-clicking launches the CLI (a
# terminal window) instead of the GUI. Keep it distinct: "hexplayer-cli".
a_cli = Analysis(
    [os.path.join(SRC_DIR, "hexplayer_cli.py")],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz_cli = PYZ(a_cli.pure)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="hexplayer-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Single COLLECT sharing the same _internal directory
coll = COLLECT(
    exe_main,
    a_main.binaries,
    a_main.datas,
    exe_host,
    a_host.binaries,
    a_host.datas,
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    strip=STRIP,
    upx=True,
    upx_exclude=[],
    name="HexPlayer",
)