import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Requires a real Linux interpreter")
@pytest.mark.parametrize(
    ("locale_name", "expected_language", "xdg_downloads"),
    [
        ("C.UTF-8", "en", False),
        ("en_US.UTF-8", "en", True),
        ("ar_EG.UTF-8", "ar", True),
    ],
)
def test_linux_startup_real_ctypes(
    tmp_path, locale_name, expected_language, xdg_downloads
):
    source = Path(__file__).resolve().parents[1] / "src"
    home = tmp_path / "home"
    config = tmp_path / "config"
    data = tmp_path / "data"
    for directory in (home, config, data):
        directory.mkdir()
    if xdg_downloads:
        (config / "user-dirs.dirs").write_text(
            'XDG_DOWNLOAD_DIR="$HOME/Custom Downloads"\n', encoding="utf-8"
        )
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(config),
        XDG_DATA_HOME=str(data),
        LC_ALL=locale_name,
        LC_MESSAGES=locale_name,
        LANG=locale_name,
    )
    script = dedent(
        """
        import _ctypes
        import ctypes
        import ctypes.util
        import os
        import sys
        import types
        from pathlib import Path

        assert sys.platform == "linux"
        assert isinstance(ctypes, types.ModuleType)
        assert ctypes.Structure is _ctypes.Structure
        assert not hasattr(ctypes, "windll")
        assert not hasattr(ctypes, "WinDLL")
        native_cdll = ctypes.CDLL
        source = Path(sys.argv[1])
        sys.path.insert(0, str(source))
        wx = types.ModuleType("wx")
        wx.LANGUAGE_ARABIC = 1
        wx.LANGUAGE_ENGLISH = 2
        sys.modules["wx"] = wx

        import language_handler
        import paths
        import settings_handler
        from media_player import mpv_backend

        assert language_handler.ctypes is ctypes
        assert mpv_backend.ctypes is ctypes
        assert ctypes.CDLL is native_cdll
        assert not hasattr(ctypes, "windll")
        assert issubclass(mpv_backend.MpvNode, ctypes.Structure)
        assert issubclass(mpv_backend.MpvNodeUnion, ctypes.Union)
        node = mpv_backend.MpvNode()
        node.format = mpv_backend.MPV_FORMAT_INT64
        node.u.int64 = 2**40
        pointer = ctypes.pointer(node)
        assert pointer.contents.u.int64 == 2**40
        assert ctypes.sizeof(node) > ctypes.sizeof(ctypes.c_int64)
        assert mpv_backend._mpv_lib is None
        assert language_handler.get_default_language() == sys.argv[2]
        assert language_handler._("startup") == "startup"
        assert Path(paths.get_app_path()) == source
        assert Path(paths.get_config_root()) == Path(os.environ["XDG_CONFIG_HOME"])
        assert Path(paths.get_data_root()) == Path(os.environ["XDG_DATA_HOME"])
        expected_settings = source / "data" if paths.portable else Path(os.environ["XDG_DATA_HOME"]) / "HexPlayer"
        assert Path(paths.settings_path) == expected_settings
        assert Path(paths.pot_provider_exe).name == "bgutil-pot"
        assert Path(paths.deno_install_path).name == "deno"
        expected_download = Path(os.environ["HOME"]) / sys.argv[3] / "HexPlayer"
        assert Path(paths.get_default_download_dir()) == expected_download
        assert Path(settings_handler.defaults["path"]) == expected_download
        assert settings_handler.defaults["lang"] == sys.argv[2]
        assert settings_handler.defaults["audiooutputdevice"] == ""
        assert settings_handler.defaults["volume"] == 100
        print("linux-startup-ok")
        """
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(source),
            expected_language,
            "Custom Downloads" if xdg_downloads else "Downloads",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "linux-startup-ok"


def test_rpm_spec_template_content_and_substitution(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec_in = root / "packaging" / "linux" / "hexplayer.spec.in"
    assert spec_in.is_file(), f"Spec template {spec_in} must exist"

    template = spec_in.read_text(encoding="utf-8")
    assert "@VERSION@" in template

    rendered = template.replace("@VERSION@", "4.8.0")
    assert "Name: hexplayer" in rendered
    assert "Version: 4.8.0" in rendered
    assert "Release: 1%{?dist}" in rendered
    assert "Summary: Accessible YouTube browser, player, and downloader" in rendered
    assert "License: MIT" in rendered
    assert (
        "URL: https://github.com/makhlwf/accessible_youtube_downloader_pro" in rendered
    )

    required_deps = [
        "gtk3",
        "mpv-libs",
        "ffmpeg-free",
        "speech-dispatcher",
        "speech-dispatcher-libs",
        "speech-dispatcher-espeak-ng",
        "at-spi2-core",
        "libnotify",
        "libsecret",
        "webkit2gtk4.1",
        "mesa-libGLU",
        "libSM",
        "libXtst",
        "xdg-utils",
        "xclip",
        "wl-clipboard",
    ]
    for dep in required_deps:
        assert dep in rendered, f"Dependency {dep} missing from Requires"

    assert "%post" in rendered
    assert "%postun" in rendered
    assert "update-desktop-database" in rendered

    for file_path in (
        "/opt/hexplayer",
        "/usr/bin/hexplayer",
        "/usr/bin/hexplayer-native-host",
        "/usr/share/applications/hexplayer.desktop",
    ):
        assert file_path in rendered, f"Path {file_path} missing from %files"


def test_rpm_spec_package_rpm_helper(tmp_path, monkeypatch):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    build_path = root / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", build_path)
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    assert hasattr(build_mod, "package_rpm"), "build.py must define package_rpm helper"

    dist_dir = tmp_path / "dist"
    build_dir = tmp_path / "build"
    dist_dir.mkdir()
    build_dir.mkdir()

    monkeypatch.setattr(build_mod, "DIST_DIR", dist_dir)
    monkeypatch.setattr(build_mod, "BUILD_DIR", build_dir)

    staging = build_dir / "deb"
    app_dir = staging / "opt" / "hexplayer"
    app_dir.mkdir(parents=True)
    (app_dir / "HexPlayer").write_text("binary", encoding="utf-8")
    (app_dir / "HexPlayerNativeHost").write_text("binary", encoding="utf-8")
    internal_dir = app_dir / "_internal"
    internal_dir.mkdir()
    (internal_dir / "libtest.so").write_text("lib", encoding="utf-8")

    bin_dir = staging / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "hexplayer").write_text("symlink-target", encoding="utf-8")
    (bin_dir / "hexplayer-native-host").write_text("symlink-target", encoding="utf-8")

    desktop_dir = staging / "usr" / "share" / "applications"
    desktop_dir.mkdir(parents=True)
    (desktop_dir / "hexplayer.desktop").write_text("desktop", encoding="utf-8")

    assets = root / "packaging" / "linux"

    recorded_commands = []

    def fake_run(cmd, *args, **kwargs):
        recorded_commands.append(cmd)
        # Find where rpmbuild would put the rpm and generate a dummy file
        rpm_topdir = None
        for i, arg in enumerate(cmd):
            if arg == "_topdir" and i + 1 < len(cmd):
                rpm_topdir = Path(cmd[i + 1])
            elif arg.startswith("_topdir "):
                rpm_topdir = Path(arg.split(None, 1)[1])
        if rpm_topdir is None:
            rpm_topdir = build_dir / "rpmbuild"
        rpms_dir = rpm_topdir / "RPMS" / "x86_64"
        rpms_dir.mkdir(parents=True, exist_ok=True)
        fake_rpm = rpms_dir / "hexplayer-4.8.0-1.fc43.x86_64.rpm"
        fake_rpm.write_bytes(b"\xed\xab\xee\xdbRPMDATA")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    rpm_path = build_mod.package_rpm(
        version="4.8.0",
        architecture="x86_64",
        staging=staging,
        assets=assets,
    )

    expected_rpm = dist_dir / "HexPlayer-4.8.0-1.x86_64.rpm"
    assert rpm_path == expected_rpm
    assert rpm_path.is_file()
    assert rpm_path.read_bytes() == b"\xed\xab\xee\xdbRPMDATA"

    # Verify rpmbuild invocation
    assert len(recorded_commands) == 1
    cmd = recorded_commands[0]
    assert cmd[0] == "rpmbuild"
    assert "-bb" in cmd
    assert "--buildroot" in cmd
    assert "--target" in cmd
    assert "x86_64" in cmd


def test_rpm_spec_ensure_mpv_runtime_and_arch_detection(monkeypatch):
    import ctypes.util
    import importlib.util
    import shutil

    root = Path(__file__).resolve().parents[1]
    build_path = root / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", build_path)
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ctypes.util, "find_library", lambda lib: "/usr/lib/libmpv.so.2")
    monkeypatch.setattr(ctypes, "CDLL", lambda path: None)

    # 1. Missing rpmbuild raises RuntimeError
    def which_no_rpmbuild(cmd):
        if cmd == "rpmbuild":
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr(shutil, "which", which_no_rpmbuild)
    with pytest.raises(RuntimeError, match="rpmbuild"):
        build_mod.ensure_mpv_runtime()

    # 2. On Ubuntu (dpkg present), missing dpkg-deb raises RuntimeError
    def which_ubuntu_no_dpkg_deb(cmd):
        if cmd == "dpkg-deb":
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr(shutil, "which", which_ubuntu_no_dpkg_deb)
    with pytest.raises(RuntimeError, match="dpkg-deb"):
        build_mod.ensure_mpv_runtime()

    # 3. On Fedora (dpkg absent, dpkg-deb absent, rpmbuild present), ensure_mpv_runtime succeeds
    def which_fedora(cmd):
        if cmd in ("dpkg", "dpkg-deb"):
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr(shutil, "which", which_fedora)
    # Should not raise
    build_mod.ensure_mpv_runtime()


def test_rpm_spec_package_linux_flow(tmp_path, monkeypatch):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    build_path = root / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", build_path)
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    dist_dir = tmp_path / "dist"
    build_dir = tmp_path / "build"
    package_dir = tmp_path / "HexPlayer"
    dist_dir.mkdir()
    build_dir.mkdir()
    package_dir.mkdir()
    (package_dir / "HexPlayer").write_text("bin", encoding="utf-8")
    (package_dir / "HexPlayerNativeHost").write_text("bin", encoding="utf-8")

    monkeypatch.setattr(build_mod, "DIST_DIR", dist_dir)
    monkeypatch.setattr(build_mod, "BUILD_DIR", build_dir)
    monkeypatch.setattr(build_mod, "PACKAGE_DIR", package_dir)
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    # Simulate Fedora environment: dpkg is absent, rpmbuild is present
    def which_fedora(cmd):
        if cmd in ("dpkg", "dpkg-deb"):
            return None
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr(shutil, "which", which_fedora)

    # Mock package_rpm to return an rpm artifact
    fake_rpm_path = dist_dir / "HexPlayer-4.8.0-1.x86_64.rpm"

    def mock_package_rpm(version, architecture, staging, assets):
        fake_rpm_path.write_bytes(b"\xed\xab\xee\xdbRPMCONTENTS")
        return fake_rpm_path

    monkeypatch.setattr(build_mod, "package_rpm", mock_package_rpm)

    # Run package_linux
    build_mod.package_linux()

    # Check generated files
    assert fake_rpm_path.is_file()
    rpm_sha = dist_dir / "HexPlayer-4.8.0-1.x86_64.rpm.sha256"
    assert rpm_sha.is_file()
    sha_content = rpm_sha.read_text(encoding="utf-8")
    assert "HexPlayer-4.8.0-1.x86_64.rpm" in sha_content

    # Check tarball
    tarball = dist_dir / "HexPlayer-4.8.0-linux-x86_64.tar.gz"
    assert tarball.is_file()
    assert (dist_dir / "HexPlayer-4.8.0-linux-x86_64.tar.gz.sha256").is_file()

    # deb should not have been generated on Fedora without dpkg-deb
    assert not (dist_dir / "HexPlayer-4.8.0-linux-amd64.deb").exists()


def test_rpm_spec_package_linux_flow_ubuntu(tmp_path, monkeypatch):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    build_path = root / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("build_script", build_path)
    build_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_mod)

    dist_dir = tmp_path / "dist"
    build_dir = tmp_path / "build"
    package_dir = tmp_path / "HexPlayer"
    dist_dir.mkdir()
    build_dir.mkdir()
    package_dir.mkdir()
    (package_dir / "HexPlayer").write_text("bin", encoding="utf-8")
    (package_dir / "HexPlayerNativeHost").write_text("bin", encoding="utf-8")

    monkeypatch.setattr(build_mod, "DIST_DIR", dist_dir)
    monkeypatch.setattr(build_mod, "BUILD_DIR", build_dir)
    monkeypatch.setattr(build_mod, "PACKAGE_DIR", package_dir)
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    # Simulate Ubuntu environment: dpkg, dpkg-deb, and rpmbuild all present
    monkeypatch.setattr(shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kwargs: "amd64\n")

    def fake_run(cmd, *args, **kwargs):
        if "dpkg-deb" in cmd[0]:
            target_deb = Path(cmd[-1])
            target_deb.write_bytes(b"!<arch>\ndebian-binary")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    fake_rpm_path = dist_dir / "HexPlayer-4.8.0-1.x86_64.rpm"

    def mock_package_rpm(version, architecture, staging, assets):
        fake_rpm_path.write_bytes(b"\xed\xab\xee\xdbRPMCONTENTS")
        return fake_rpm_path

    monkeypatch.setattr(build_mod, "package_rpm", mock_package_rpm)

    # Run package_linux
    build_mod.package_linux()

    # All three artifacts should be produced with their .sha256 files
    tarball = dist_dir / "HexPlayer-4.8.0-linux-x86_64.tar.gz"
    deb = dist_dir / "HexPlayer-4.8.0-linux-amd64.deb"
    rpm = dist_dir / "HexPlayer-4.8.0-1.x86_64.rpm"

    assert tarball.is_file()
    assert deb.is_file()
    assert rpm.is_file()

    for artifact in (tarball, deb, rpm):
        sha_file = artifact.with_name(artifact.name + ".sha256")
        assert sha_file.is_file()
        assert artifact.name in sha_file.read_text(encoding="utf-8")
