"""Build script to bundle and compile the lightweight standalone YouTube service.

Produces a ~6.15 MB single-file executable (`src/youtube_service.exe` on Windows or
`src/youtube_service` on Linux) embedding QuickJS-ng, libuv, and YouTube.js.
"""

import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
BUILD_DIR = ROOT / "build" / "js_service"
POLYFILL_PATH = SRC_DIR / "polyfill.js"
SERVICE_PATH = SRC_DIR / "service.js"

TXIKI_VERSION = "v26.6.0"
TXIKI_WIN_URL = f"https://github.com/saghul/txiki.js/releases/download/{TXIKI_VERSION}/txiki-windows-x86_64.zip"


def ensure_tjs_binary():
    """Ensure tjs.exe (txiki.js) is available in BUILD_DIR."""
    exe_name = "tjs.exe" if sys.platform == "win32" else "tjs"
    cached_tjs = BUILD_DIR / exe_name
    if cached_tjs.is_file():
        return str(cached_tjs)

    system_tjs = shutil.which("tjs")
    if system_tjs:
        return system_tjs

    if sys.platform != "win32":
        raise RuntimeError(
            "Pre-built txiki binary is currently automated for Windows. "
            "On Linux, install txiki (tjs) via your package manager."
        )

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    zip_dest = BUILD_DIR / "txiki.zip"
    print(f"Downloading txiki.js runtime ({TXIKI_VERSION})...")
    req = urllib.request.Request(TXIKI_WIN_URL, headers={"User-Agent": "HexPlayer"})
    with urllib.request.urlopen(req) as resp, open(zip_dest, "wb") as out:
        shutil.copyfileobj(resp, out)

    with zipfile.ZipFile(zip_dest, "r") as archive:
        archive.extractall(BUILD_DIR)

    # Find tjs.exe inside extracted directory
    found = list(BUILD_DIR.rglob(exe_name))
    if not found:
        raise RuntimeError(f"Could not find {exe_name} in extracted archive")

    final_tjs = BUILD_DIR / exe_name
    if found[0] != final_tjs:
        shutil.copy2(found[0], final_tjs)

    if zip_dest.exists():
        zip_dest.unlink()

    return str(final_tjs)


def ensure_npm_packages():
    """Ensure youtubei.js is installed in BUILD_DIR/node_modules."""
    modules_dir = BUILD_DIR / "node_modules" / "youtubei.js"
    if modules_dir.is_dir():
        return

    pkg_json = BUILD_DIR / "package.json"
    if not pkg_json.is_file():
        with open(pkg_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "name": "hexplayer-youtube-service-builder",
                    "dependencies": {"youtubei.js": "18.1.0"},
                },
                f,
                indent=2,
            )

    print("Installing youtubei.js dependency in build cache...")
    subprocess.run(
        "npm install",
        cwd=str(BUILD_DIR),
        shell=True,
        check=True,
    )


def build():
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    tjs_bin = ensure_tjs_binary()
    ensure_npm_packages()

    staged_service = BUILD_DIR / "service.js"
    staged_poly = BUILD_DIR / "polyfill.js"
    shutil.copy2(SERVICE_PATH, staged_service)
    shutil.copy2(POLYFILL_PATH, staged_poly)

    bundle_out = BUILD_DIR / "service.bundle.js"
    exe_name = "youtube_service.exe" if sys.platform == "win32" else "youtube_service"
    target_exe = SRC_DIR / exe_name

    print("Bundling service.js with esbuild via tjs...")
    bundle_cmd = [
        tjs_bin,
        "bundle",
        f"--inject:{staged_poly}",
        str(staged_service),
        str(bundle_out),
    ]
    subprocess.run(bundle_cmd, cwd=str(BUILD_DIR), check=True)

    bundle_size_kb = bundle_out.stat().st_size / 1024
    print(f"Bundle created: {bundle_out.name} ({bundle_size_kb:.1f} KB)")

    print(f"Compiling standalone executable: {target_exe.name}...")
    compile_cmd = [tjs_bin, "compile", str(bundle_out), str(target_exe)]
    subprocess.run(compile_cmd, cwd=str(BUILD_DIR), check=True)

    exe_size_mb = target_exe.stat().st_size / (1024 * 1024)
    print(
        f"Standalone executable built successfully: {target_exe} ({exe_size_mb:.2f} MB)"
    )

    # Verify execution
    print("Verifying standalone executable via JSON-RPC test ping...")
    proc = subprocess.Popen(
        [str(target_exe)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    test_req = {"id": 1, "command": "get_shorts_feed", "params": {}}
    proc.stdin.write(json.dumps(test_req) + "\n")
    proc.stdin.flush()
    resp_line = proc.stdout.readline()
    proc.kill()

    resp = json.loads(resp_line)
    if resp.get("id") != 1:
        raise RuntimeError(f"Unexpected verification response: {resp_line}")

    print("Verification passed! Standalone service is functional.")
    return target_exe


if __name__ == "__main__":
    try:
        build()
    except Exception as err:
        print(f"Build failed: {err}", file=sys.stderr)
        sys.exit(1)
