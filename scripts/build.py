import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "src")
DIST_DIR = os.path.join(ROOT, "dist")
BUILD_DIR = os.path.join(ROOT, "build")

SPEC_PATH = os.path.join(ROOT, "HexPlayer.spec")

if not os.path.isdir(SRC_DIR):
    print("Error: This script should be run from the root of the repository.")
    sys.exit(1)

if not os.path.isfile(SPEC_PATH):
    print(f"Error: Spec file not found: {SPEC_PATH}")
    sys.exit(1)

mpv_dll = os.path.join(SRC_DIR, "libmpv-2.dll")
mpv_archive = os.path.join(SRC_DIR, "libmpv-2.dll.zip")


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

for build_output_dir in (DIST_DIR, BUILD_DIR):
    if os.path.exists(build_output_dir):
        shutil.rmtree(build_output_dir)

app_name = "HexPlayer"
native_host_name = "HexPlayerNativeHost"
package_dir = os.path.join(DIST_DIR, app_name)

# Construct the unified pyinstaller command
command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath",
    DIST_DIR,
    "--workpath",
    BUILD_DIR,
    SPEC_PATH,
]

print(f"Running command: {' '.join(command)}")


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

    root_exe = os.path.join(DIST_DIR, f"{app_name}.exe")
    root_internal = os.path.join(DIST_DIR, "_internal")
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
        os.path.join(package_dir, "_internal", "prism", "_native", "_prism_cffi.pyd"),
        os.path.join(package_dir, "_internal", "prism", "_native", "prism.dll"),
    ]
    missing_paths = [path for path in required_paths if not os.path.exists(path)]
    internal_dir = os.path.join(package_dir, "_internal")
    has_cffi_backend = (
        any(
            f.startswith("_cffi_backend") and f.endswith(".pyd")
            for f in os.listdir(internal_dir)
        )
        if os.path.isdir(internal_dir)
        else False
    )
    if not has_cffi_backend:
        missing_paths.append(
            os.path.join(package_dir, "_internal", "_cffi_backend*.pyd")
        )

    if missing_paths:
        missing_list = "\n".join(f"- {path}" for path in missing_paths)
        raise RuntimeError(
            "Build output is incomplete. The installer would be broken.\n"
            f"Missing paths:\n{missing_list}"
        )


# Run the command
try:
    subprocess.run(command, cwd=ROOT, check=True)
    normalize_main_build_output()
    validate_package_layout()
    print("Build completed successfully!")
    print(f"The package directory is: {package_dir}")
except subprocess.CalledProcessError as e:
    print(f"Build failed with error: {e}")
    sys.exit(1)
except RuntimeError as e:
    print(f"Build failed: {e}")
    sys.exit(1)
except FileNotFoundError:
    print("Error: pyinstaller is not installed or not in the system's PATH.")
    print("Please install it using: uv sync --no-dev --group build")
    sys.exit(1)
