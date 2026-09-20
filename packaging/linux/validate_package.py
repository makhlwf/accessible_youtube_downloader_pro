import argparse
import ctypes
import ctypes.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SUCCESS = "HexPlayer packaging smoke passed: GTK, Prism import, offline audio EOF"


def check_application(executable, host, directory):
    home = directory / "isolated home"
    home.mkdir()
    environment = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "DBUS_SESSION_BUS_ADDRESS",
    ):
        environment.pop(key, None)
    environment["HOME"] = str(home)
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        path = home / name
        path.mkdir(mode=0o700)
        environment[key] = str(path)
    for path in (executable, host):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Missing or non-executable packaged binary: {path}")
    result = subprocess.run(
        [
            "timeout",
            "--kill-after=10s",
            "60s",
            "dbus-run-session",
            "--",
            "xvfb-run",
            "-a",
            str(executable),
            "--packaging-smoke-test",
        ],
        cwd=home,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=80,
    )
    print(result.stdout, end="", flush=True)
    print(result.stderr, end="", file=sys.stderr, flush=True)
    if result.returncode != 0 or SUCCESS not in result.stdout:
        raise RuntimeError(
            f"Packaged runtime smoke failed for {executable}: exit {result.returncode}"
        )
    payload = json.dumps({"type": "packaging_smoke_test"}).encode("utf-8")
    result = subprocess.run(
        ["timeout", "--kill-after=5s", "30s", str(host)],
        input=struct.pack("<I", len(payload)) + payload,
        cwd=home,
        env=environment,
        capture_output=True,
        check=False,
        timeout=40,
    )
    if result.returncode != 1 or len(result.stdout) < 4:
        raise RuntimeError(
            f"Native host failed: exit {result.returncode}; stderr={result.stderr!r}; "
            f"stdout={result.stdout!r}"
        )
    size = struct.unpack("<I", result.stdout[:4])[0]
    if size != len(result.stdout) - 4:
        raise RuntimeError("Native host response has invalid framing or extra stdout")
    response = json.loads(result.stdout[4:])
    if response != {"ok": False, "error": "Unsupported message type"}:
        raise RuntimeError(f"Unexpected offline native host response: {response!r}")
    print(f"Packaged executable and offline native host protocol passed: {executable}")


def check_accessibility():
    """Verify accessibility infrastructure availability (Speech Dispatcher & AT-SPI2)."""
    # 1. Speech Dispatcher check
    speechd_lib = ctypes.util.find_library("speechd")
    spd_bin = shutil.which("spd-say") or shutil.which("speech-dispatcher")
    if not speechd_lib and not spd_bin:
        print(
            "Notice: Neither libspeechd nor speech-dispatcher binary found",
            file=sys.stderr,
        )
    else:
        info = []
        if speechd_lib:
            info.append(f"lib={speechd_lib}")
        if spd_bin:
            info.append(f"bin={spd_bin}")
        print(f"Speech Dispatcher accessibility component verified: {', '.join(info)}")

    # 2. AT-SPI2 Accessibility bus launcher check
    atspi_paths = [
        "at-spi-bus-launcher",
        "/usr/libexec/at-spi-bus-launcher",
        "/usr/lib/at-spi2-core/at-spi-bus-launcher",
        "/usr/lib/at-spi2/at-spi-bus-launcher",
    ]
    found_atspi = None
    for p in atspi_paths:
        if shutil.which(p) or Path(p).is_file():
            found_atspi = p
            break
    if found_atspi:
        print(f"AT-SPI2 accessibility component verified: {found_atspi}")
    else:
        print(
            "Notice: AT-SPI2 bus launcher not found in standard paths", file=sys.stderr
        )


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--installed", action="store_true")
    group.add_argument("--tarball", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() == 0:
        parser.error("Linux package validation must run as a normal, non-root user")
    with tempfile.TemporaryDirectory(prefix="hexplayer package smoke ") as temporary:
        directory = Path(temporary)
        if args.installed:
            executable = Path("/usr/bin/hexplayer")
            host = Path("/usr/bin/hexplayer-native-host")
            desktop = Path("/usr/share/applications/hexplayer.desktop")
            if not desktop.is_file():
                raise RuntimeError(f"Missing installed desktop file: {desktop}")
            desktop_validator = shutil.which("desktop-file-validate")
            if desktop_validator:
                res = subprocess.run(
                    [desktop_validator, str(desktop)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode != 0:
                    raise RuntimeError(f"Desktop file validation failed: {res.stderr}")
                print(f"Installed desktop file validated: {desktop}")
            opt_dir = Path("/opt/hexplayer")
            if not opt_dir.is_dir():
                raise RuntimeError(f"Missing installed directory: {opt_dir}")
            if shutil.which("rpm"):
                res = subprocess.run(
                    ["rpm", "-q", "hexplayer"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    print(f"RPM package verified: {res.stdout.strip()}")
            elif shutil.which("dpkg-query"):
                res = subprocess.run(
                    ["dpkg-query", "-W", "-f=${Status}", "hexplayer"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0 and "installed" in res.stdout:
                    print(f"Debian package verified: {res.stdout.strip()}")
        else:
            extracted = directory / "tar extraction with spaces"
            extracted.mkdir()
            with tarfile.open(args.tarball, "r:gz") as archive:
                archive.extractall(extracted, filter="data")
            executable = extracted / "HexPlayer" / "HexPlayer"
            host = executable.with_name("HexPlayerNativeHost")
        check_accessibility()
        check_application(executable, host, directory)


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        RuntimeError,
        tarfile.TarError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Linux package validation FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
