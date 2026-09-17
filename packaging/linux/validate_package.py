import argparse
import json
import os
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
        else:
            extracted = directory / "tar extraction with spaces"
            extracted.mkdir()
            with tarfile.open(args.tarball, "r:gz") as archive:
                archive.extractall(extracted, filter="data")
            executable = extracted / "HexPlayer" / "HexPlayer"
            host = executable.with_name("HexPlayerNativeHost")
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
