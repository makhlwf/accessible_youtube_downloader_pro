import os
import shutil
import subprocess
import sys
import zipfile

# It's better to run this from the repo root.
if not os.path.exists("source"):
    print("Error: This script should be run from the root of the repository.")
    exit(1)

mpv_dll = os.path.join("source", "libmpv-2.dll")
mpv_archive = os.path.join("source", "libmpv-2.dll.zip")


def ensure_mpv_runtime():
    if os.path.exists(mpv_dll):
        return
    if not os.path.exists(mpv_archive):
        raise RuntimeError("libmpv-2.dll or libmpv-2.dll.zip is required to build")

    print("Extracting libmpv-2.dll from bundled archive...")
    with zipfile.ZipFile(mpv_archive) as archive:
        member = next(
            (
                name
                for name in archive.namelist()
                if os.path.basename(name).lower() == "libmpv-2.dll"
            ),
            None,
        )
        if member is None:
            raise RuntimeError("libmpv-2.dll.zip does not contain libmpv-2.dll")
        with archive.open(member) as source, open(mpv_dll, "wb") as target:
            shutil.copyfileobj(source, target)


ensure_mpv_runtime()

# Clean up previous builds
if os.path.exists("dist"):
    shutil.rmtree("dist")
if os.path.exists("build"):
    shutil.rmtree("build")

# The entry point of the application
entry_point = os.path.join("source", "accessible_youtube_downloader_pro.py")
native_host_entry_point = os.path.join("source", "native_messaging_host.py")

# Name of the output executable
app_name = "HexPlayer"
native_host_name = "HexPlayerNativeHost"
package_dir = os.path.join("dist", app_name)

# Native runtime files must be added as binaries so PyInstaller handles them
# with the same layout and loader semantics as extension modules.
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
    "nvdaControllerClient64.dll",
]

system_binary_files = [
    # libmpv imports the Vulkan loader. Many end-user systems do not have it,
    # and Windows reports that failure as libmpv-2.dll not being found.
    "vulkan-1.dll",
]

# Data files and directories to be included.
data_to_add = [
    "deno.json",
    "deno.lock",
    "service.js",
    "update_history.js",
    "../PRIVACY_POLICY.md",
    # Directories
    "assets",
    "browser_extension",
    "docs",
    "languages",
]


def source_item_path(item):
    return os.path.normpath(os.path.join("source", item))


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


# ------------------------------------------------------------------
# THE NUCLEAR LIST: Forces PyInstaller to include the full StdLib
# required for dynamic loading of complex packages like yt-dlp
# ------------------------------------------------------------------
stdlib_hidden_imports = [
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
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--name",
    app_name,
    "--distpath",
    "dist",
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

# Add binary files
for item in binary_files:
    source_path = source_item_path(item)
    if not os.path.isfile(source_path):
        raise RuntimeError(f"Required runtime file is missing: {source_path}")
    command.extend(["--add-binary", f"{source_path}{os.pathsep}."])

for dll_name in system_binary_files:
    source_path = find_system_dll(dll_name)
    if not source_path:
        raise RuntimeError(
            f"Required system runtime is missing: {dll_name}. "
            "Install the Vulkan Runtime or use a libmpv build that does not "
            "import vulkan-1.dll."
        )
    command.extend(["--add-binary", f"{source_path}{os.pathsep}."])
    print(f"Bundling system runtime: {source_path}")

# Add data files
for item in data_to_add:
    source_path = source_item_path(item)

    if os.path.isdir(source_path):
        command.extend(["--add-data", f"{source_path}{os.pathsep}{item}"])
    elif os.path.isfile(source_path):
        command.extend(["--add-data", f"{source_path}{os.pathsep}."])

# Add the entry point script at the end
command.append(entry_point)

native_host_command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name",
    native_host_name,
    "--console",
    "--onefile",
    "--distpath",
    package_dir,
    "--workpath",
    os.path.join("build", native_host_name),
    "--specpath",
    os.path.join("build", native_host_name),
    native_host_entry_point,
]

print(f"Running command: {' '.join(command)}")
print(f"Running command: {' '.join(native_host_command)}")


def normalize_main_build_output():
    expected_exe = os.path.join(package_dir, f"{app_name}.exe")
    expected_internal = os.path.join(package_dir, "_internal")
    if os.path.exists(expected_exe) and os.path.isdir(expected_internal):
        return

    nested_dir = os.path.join(package_dir, app_name)
    nested_exe = os.path.join(nested_dir, f"{app_name}.exe")
    nested_internal = os.path.join(nested_dir, "_internal")
    if os.path.exists(nested_exe) and os.path.isdir(nested_internal):
        for item in os.listdir(nested_dir):
            shutil.move(os.path.join(nested_dir, item), os.path.join(package_dir, item))
        os.rmdir(nested_dir)
        return

    root_exe = os.path.join("dist", f"{app_name}.exe")
    root_internal = os.path.join("dist", "_internal")
    if os.path.exists(root_exe) and os.path.isdir(root_internal):
        os.makedirs(package_dir, exist_ok=True)
        shutil.move(root_exe, expected_exe)
        shutil.move(root_internal, expected_internal)
        return

    raise RuntimeError("Could not find the main PyInstaller output layout to package.")


def validate_package_layout():
    required_paths = [
        os.path.join(package_dir, f"{app_name}.exe"),
        os.path.join(package_dir, f"{native_host_name}.exe"),
        os.path.join(package_dir, "_internal"),
        os.path.join(package_dir, "_internal", "browser_extension", "manifest.json"),
    ]
    missing_paths = [path for path in required_paths if not os.path.exists(path)]
    if missing_paths:
        missing_list = "\n".join(f"- {path}" for path in missing_paths)
        raise RuntimeError(
            "Build output is incomplete. The installer would be broken.\n"
            f"Missing paths:\n{missing_list}"
        )


# Run the command
try:
    subprocess.run(command, check=True)
    normalize_main_build_output()
    subprocess.run(native_host_command, check=True)
    validate_package_layout()
    print("Build completed successfully!")
    print(f"The package directory is: {package_dir}")
except subprocess.CalledProcessError as e:
    print(f"Build failed with error: {e}")
    exit(1)
except RuntimeError as e:
    print(f"Build failed: {e}")
    exit(1)
except FileNotFoundError:
    print("Error: pyinstaller is not installed or not in the system's PATH.")
    print("Please install it using: pip install pyinstaller")
    exit(1)
