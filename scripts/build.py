import argparse
import ctypes
import ctypes.util
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_PATH = ROOT / "HexPlayer.spec"
APP_NAME = "HexPlayer"
HOST_NAME = "HexPlayerNativeHost"
PACKAGE_DIR = DIST_DIR / APP_NAME


def ensure_mpv_runtime():
    if sys.platform == "linux":
        library = ctypes.util.find_library("mpv")
        if not library:
            raise RuntimeError("Install system libmpv (Ubuntu 24.04: libmpv2).")
        ctypes.CDLL(library)
        for command in ("ffmpeg", "ffprobe", "dpkg-deb"):
            if not shutil.which(command):
                raise RuntimeError(f"Required Linux build command not found: {command}")
        return
    mpv_dll = SRC_DIR / "libmpv-2.dll"
    mpv_archive = SRC_DIR / "libmpv-2.dll.zip"
    if mpv_dll.exists():
        return
    if not mpv_archive.exists():
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
        with archive.open(member) as source, mpv_dll.open("wb") as target:
            shutil.copyfileobj(source, target)


def executable_name(name):
    return f"{name}.exe" if sys.platform == "win32" else name


def normalize_main_build_output():
    expected_exe = PACKAGE_DIR / executable_name(APP_NAME)
    expected_internal = PACKAGE_DIR / "_internal"
    if expected_exe.is_file() and expected_internal.is_dir():
        return
    nested_dir = PACKAGE_DIR / APP_NAME
    if (nested_dir / executable_name(APP_NAME)).is_file() and (
        nested_dir / "_internal"
    ).is_dir():
        for item in nested_dir.iterdir():
            shutil.move(item, PACKAGE_DIR / item.name)
        nested_dir.rmdir()
        return
    root_exe = DIST_DIR / executable_name(APP_NAME)
    root_internal = DIST_DIR / "_internal"
    if root_exe.is_file() and root_internal.is_dir():
        PACKAGE_DIR.mkdir(exist_ok=True)
        shutil.move(root_exe, expected_exe)
        shutil.move(root_internal, expected_internal)
        return
    raise RuntimeError("Could not find the main PyInstaller output layout to package.")


def validate_package_layout():
    internal = PACKAGE_DIR / "_internal"
    required = [
        PACKAGE_DIR / executable_name(APP_NAME),
        PACKAGE_DIR / executable_name(HOST_NAME),
        internal / "browser_extension" / "manifest.json",
    ]
    patterns = [
        "_cffi_backend*.pyd",
        "prism/_native/_prism_cffi.pyd",
        "prism/_native/prism.dll",
    ]
    if sys.platform == "linux":
        patterns = [
            "_cffi_backend*.so",
            "prism/_native/_prism_cffi*.so",
            "prism/_native/libprism.so*",
        ]
        for name in (APP_NAME, HOST_NAME):
            executable = PACKAGE_DIR / name
            if executable.is_file():
                with executable.open("rb") as stream:
                    if stream.read(4) != b"\x7fELF" or not os.access(
                        executable, os.X_OK
                    ):
                        raise RuntimeError(
                            f"Not an executable ELF binary: {executable}"
                        )
        foreign_files = [
            path
            for path in PACKAGE_DIR.rglob("*")
            if path.suffix.lower() in {".dll", ".exe", ".pyd"}
        ]
        if foreign_files:
            raise RuntimeError(
                f"Windows binaries found in Linux package: {foreign_files}"
            )
    missing = [str(path) for path in required if not path.is_file()]
    missing.extend(
        str(internal / pattern)
        for pattern in patterns
        if not any(internal.glob(pattern))
    )
    if missing:
        raise RuntimeError(
            "Build output is incomplete. Missing paths:\n" + "\n".join(missing)
        )


def package_linux():
    assets = ROOT / "packaging" / "linux"
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    architecture = subprocess.check_output(
        ["dpkg", "--print-architecture"], text=True
    ).strip()
    if architecture != "amd64" or platform.machine() != "x86_64":
        raise RuntimeError(
            "Linux release packaging currently supports native amd64 only."
        )
    shutil.copy2(ROOT / "LICENSE", PACKAGE_DIR / "LICENSE")
    archive_path = DIST_DIR / f"HexPlayer-{version}-linux-x86_64.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(PACKAGE_DIR, arcname=APP_NAME)
    staging = BUILD_DIR / "deb"
    app_dir = staging / "opt" / "hexplayer"
    shutil.copytree(PACKAGE_DIR, app_dir, symlinks=True)
    bin_dir = staging / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "hexplayer").symlink_to("/opt/hexplayer/HexPlayer")
    (bin_dir / "hexplayer-native-host").symlink_to("/opt/hexplayer/HexPlayerNativeHost")
    desktop_dir = staging / "usr" / "share" / "applications"
    desktop_dir.mkdir(parents=True)
    shutil.copy2(assets / "hexplayer.desktop", desktop_dir / "hexplayer.desktop")
    metadata_dir = staging / "DEBIAN"
    metadata_dir.mkdir()
    control = (assets / "control.in").read_text(encoding="utf-8")
    installed_size = sum(
        path.stat().st_size for path in app_dir.rglob("*") if path.is_file()
    )
    control = control.replace("@VERSION@", version).replace("@ARCH@", architecture)
    control = control.replace("@INSTALLED_SIZE@", str((installed_size + 1023) // 1024))
    (metadata_dir / "control").write_text(control, encoding="utf-8")
    deb_path = DIST_DIR / f"HexPlayer-{version}-linux-amd64.deb"
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "--build", str(staging), str(deb_path)],
        check=True,
    )
    for artifact in (archive_path, deb_path):
        with artifact.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        artifact.with_name(artifact.name + ".sha256").write_text(
            f"{digest}  {artifact.name}\n", encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if sys.platform not in {"win32", "linux"}:
        parser.error("Only native Windows and Linux builds are supported.")
    if not SRC_DIR.is_dir() or not SPEC_PATH.is_file():
        parser.error("Source directory or PyInstaller spec is missing.")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        str(SPEC_PATH),
    ]
    print(f"Running command: {' '.join(command)}")
    if args.dry_run:
        print(f"Native target: {sys.platform}; output: {PACKAGE_DIR}")
        return 0
    try:
        ensure_mpv_runtime()
        for output_dir in (DIST_DIR, BUILD_DIR):
            if output_dir.exists():
                shutil.rmtree(output_dir)
        subprocess.run(command, cwd=ROOT, check=True)
        normalize_main_build_output()
        validate_package_layout()
        if sys.platform == "linux":
            package_linux()
        print(f"Build completed successfully: {PACKAGE_DIR}")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
