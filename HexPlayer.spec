# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_all

ROOT = os.path.abspath(SPECPATH)
SRC_DIR = os.path.join(ROOT, "src")


def src_item_path(item):
    return os.path.normpath(os.path.join(SRC_DIR, item))


def find_system_dll(name):
    search_dirs = []
    windir = os.environ.get("WINDIR")
    if windir:
        search_dirs.append(os.path.join(windir, "System32"))
    search_dirs.extend(os.environ.get("PATH", "").split(os.pathsep))

    seen = set()
    for directory in search_dirs:
        if not directory:
            continue
        directory_key = directory.casefold()
        if directory_key in seen:
            continue
        seen.add(directory_key)
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return None


# Native runtime binary files
binary_files = [
    "api-ms-win-core-path-l1-1-0.dll",
    "avcodec-60.dll",
    "avdevice-60.dll",
    "avfilter-9.dll",
    "avformat-60.dll",
    "avutil-58.dll",
    "postproc-57.dll",
    "swresample-4.dll",
    "swscale-7.dll",
    "ffmpeg.exe",
    "ffprobe.exe",
    "libmpv-2.dll",
]

system_binary_files = [
    "vulkan-1.dll",
]

binaries = []
for item in binary_files:
    source_path = src_item_path(item)
    if os.path.isfile(source_path):
        binaries.append((source_path, "."))

for dll_name in system_binary_files:
    source_path = find_system_dll(dll_name)
    if source_path:
        binaries.append((source_path, "."))

try:
    import prism

    prism_dir = os.path.dirname(prism.__file__)
    for root_path, _, filenames in os.walk(prism_dir):
        for filename in filenames:
            if filename.endswith((".pyd", ".dll")):
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

# Analysis and EXE for HexPlayer (GUI)
a_main = Analysis(
    [os.path.join(SRC_DIR, "accessible_youtube_downloader_pro.py")],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz_main = PYZ(a_main.pure)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    [],
    exclude_binaries=True,
    name="HexPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
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
    hiddenimports=[],
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
    strip=False,
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HexPlayer",
)
