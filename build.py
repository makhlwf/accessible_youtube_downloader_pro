import os
import subprocess
import shutil

# It's better to run this from the repo root.
if not os.path.exists("source"):
    print("Error: This script should be run from the root of the repository.")
    exit(1)

# Clean up previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

# The entry point of the application
entry_point = os.path.join("source", "accessible_youtube_downloader_pro.py")

# Name of the output executable
app_name = "HexPlayer"

# Data files and directories to be included
# The format is 'source_path:destination_in_bundle'
# Using os.pathsep for the separator.
data_to_add = [
    # DLLs and EXEs
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
    "libvlc.dll",
    "libvlccore.dll",
    "nvdaControllerClient64.dll",
    "deno.json",
    "deno.lock",
    "get_recommendations.js",
    "update_history.js",
    "get_watch_history.js",
    "../PRIVACY_POLICY.md",
    # Directories
    "assets",
    "docs",
    "languages",
    "plugins",
]

# ------------------------------------------------------------------
# THE NUCLEAR LIST: Forces PyInstaller to include the full StdLib
# required for dynamic loading of complex packages like yt-dlp
# ------------------------------------------------------------------
stdlib_hidden_imports = [
    # The specific ones you already hit
    "optparse",
    "getpass",
    "netrc",
    "uuid",
    "fileinput",
    "shlex",
    # Core Utilities
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
    # Text & Encoding
    "string",
    "textwrap",
    "unicodedata",
    "codecs",
    "encodings",
    "locale",
    "json",
    "csv",
    "plistlib",
    # Compression
    "gzip",
    "bz2",
    "lzma",
    "zipfile",
    "tarfile",
    "zlib",
    # Networking & Internet (CRITICAL for yt-dlp)
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
    # System & Threading
    "threading",
    "multiprocessing",
    "queue",
    "concurrent",
    "concurrent.futures",
    "logging",
    "logging.handlers",
    "sqlite3",
    # Math
    "math",
    "cmath",
    "numbers",
    "decimal",
    "fractions",
    "statistics",
    # obscure modules yt-dlp sometimes touches via 'compat'
    "colorsys",
    "curses",
    "pty",
    "tty",
    "difflib",
    "doctest",
    "pydoc",
]

# Construct the pyinstaller command
command = [
    "pyinstaller",
    "--noconfirm",
    "--name",
    app_name,
    "--noconsole",
    # Clean build
    "--clean",
]

# Add all the hidden imports
for mod in stdlib_hidden_imports:
    command.extend(["--hidden-import", mod])

# Add the Collect Submodules (More efficient for packages)
# This forces the WHOLE package, not just the top file
command.extend(["--collect-submodules", "xml"])
command.extend(["--collect-submodules", "http"])
command.extend(["--collect-submodules", "email"])
command.extend(["--collect-submodules", "urllib"])
command.extend(["--collect-submodules", "html"])
command.extend(["--collect-submodules", "encodings"])
command.extend(["--collect-submodules", "logging"])
command.extend(["--collect-submodules", "ctypes"])
command.extend(
    ["--collect-submodules", "curses"]
)  # Windows sometimes needs this for progress bars

# Add data files
for item in data_to_add:
    source_path = os.path.join("source", item)
    if os.path.isdir(source_path):
        # For directories, destination is the same as the directory name
        command.extend(["--add-data", f"{source_path}{os.pathsep}{item}"])
    elif os.path.isfile(source_path):
        # For files, destination is the root of the bundle
        command.extend(["--add-data", f"{source_path}{os.pathsep}."])

# Add the entry point script at the end
command.append(entry_point)

print(f"Running command: {' '.join(command)}")

# Run the command
try:
    subprocess.run(command, check=True)
    print("Build completed successfully!")
    print("The executable is in the 'dist' directory.")
except subprocess.CalledProcessError as e:
    print(f"Build failed with error: {e}")
    exit(1)
except FileNotFoundError:
    print("Error: pyinstaller is not installed or not in the system's PATH.")
    print("Please install it using: pip install pyinstaller")
    exit(1)
