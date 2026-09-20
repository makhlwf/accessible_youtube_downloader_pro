import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import wx

from gui import download_complete_dialog, download_dialog, settings_dialog


def test_linux_download_actions_open_default_application(monkeypatch, tmp_path):
    monkeypatch.setattr(download_complete_dialog.sys, "platform", "linux")
    opened = Mock(return_value=True)
    monkeypatch.setattr(wx, "LaunchDefaultApplication", opened, raising=False)
    dialog = object.__new__(download_complete_dialog.DownloadCompleteDialog)
    dialog.file_path = str(tmp_path / "video.mp4")
    dialog.folder_path = str(tmp_path)
    dialog.EndModal = Mock()
    dialog.on_play(None)
    opened.assert_called_with(dialog.file_path)
    dialog.on_show_file(None)
    opened.assert_called_with(str(tmp_path))
    dialog.on_open_folder(None)
    opened.assert_called_with(str(tmp_path))
    assert dialog.EndModal.call_count == 3


def test_linux_open_failure_keeps_download_dialog_open(monkeypatch):
    monkeypatch.setattr(
        wx, "LaunchDefaultApplication", Mock(return_value=False), raising=False
    )
    error = Mock()
    monkeypatch.setattr(download_complete_dialog.utils, "show_error", error)
    dialog = object.__new__(download_complete_dialog.DownloadCompleteDialog)
    dialog.file_path = "/missing.mp4"
    dialog.EndModal = Mock()
    dialog.on_play(None)
    error.assert_called_once()
    dialog.EndModal.assert_not_called()


def test_download_selectors_use_paths_default(monkeypatch, tmp_path):
    default = str(tmp_path / "downloads")
    monkeypatch.setattr(
        download_dialog.paths, "get_default_download_dir", lambda: default
    )
    selector = Mock(return_value="")
    monkeypatch.setattr(wx, "DirSelector", selector, raising=False)
    download = object.__new__(download_dialog.DownloadDialog)
    download.onChangePath(None)
    assert selector.call_args.args[1] == default
    settings = object.__new__(settings_dialog.SettingsDialog)
    settings.onChange(None)
    assert selector.call_args.args[1] == default


def test_linux_browser_integration_checkbox_enabled(monkeypatch):
    monkeypatch.setattr(settings_dialog.sys, "platform", "linux")
    monkeypatch.setattr(settings_dialog, "config_get", lambda *_: False)
    monkeypatch.setattr(
        settings_dialog.utils,
        "get_player_client_choices",
        lambda: [("default", "Default")],
    )
    dialog = object.__new__(settings_dialog.SettingsDialog)
    dialog.getPlayerClientSelection = Mock(return_value=0)
    dialog._new_page = Mock(return_value=(wx.Panel(None), wx.BoxSizer(wx.VERTICAL)))
    dialog._build_advanced_page()
    assert dialog.browserIntegration.IsEnabled()


def test_linux_integration_failure_rolls_back_preference(monkeypatch):
    monkeypatch.setattr(settings_dialog.sys, "platform", "linux")
    values = {"browser_integration": False, "pot_provider_enabled": False}
    monkeypatch.setattr(settings_dialog, "config_get", lambda key: values.get(key, "0"))
    monkeypatch.setattr(
        settings_dialog, "config_set", lambda key, value: values.update({key: value})
    )
    monkeypatch.setattr(
        settings_dialog.windows_url_association,
        "register_browser_integration",
        lambda: False,
    )
    message = Mock()
    monkeypatch.setattr(wx, "MessageBox", message)
    dialog = object.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {"browser_integration": True}
    dialog.validate_cookies_path = lambda *_: True
    dialog.audioQuality2 = SimpleNamespace(Selection=0)
    dialog.formats = SimpleNamespace(Selection=0)
    dialog.videoQuality = SimpleNamespace(Selection=0)
    dialog.audioQuality = SimpleNamespace(Selection=0)
    dialog.audioOutputDevices = [{"id": ""}]
    dialog.audioOutputDevice = SimpleNamespace(Selection=0)
    dialog.playbackSpeedStep = Mock()
    dialog._save_sponsorblock_settings = Mock()
    dialog.theme_keys = ["System Default"]
    dialog.themeBox = SimpleNamespace(Selection=0)
    dialog.languageBox = SimpleNamespace(
        Selection=0, GetStringSelection=Mock(return_value="en")
    )
    dialog.Destroy = Mock()
    dialog.EndModal = Mock()
    dialog.onOk(None)
    assert values["browser_integration"] is False
    assert "browser integration" in message.call_args_list[0].args[0]


def parse_os_release_distro(os_release_content: str) -> str:
    """Parse /etc/os-release content and determine the distribution family."""
    values = {}
    for line in os_release_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip().strip("\"'")

    target_id = values.get("ID", "")
    target_like = values.get("ID_LIKE", "")
    combined = f" {target_id} {target_like} "
    for fedora_distro in ("fedora", "rhel", "centos", "rocky", "almalinux"):
        if f" {fedora_distro} " in combined:
            return "fedora"
    for debian_distro in ("ubuntu", "debian", "linuxmint", "pop"):
        if f" {debian_distro} " in combined:
            return "debian"
    return "unknown"


def test_detect_distro_script_content():
    script_path = (
        Path(__file__).resolve().parents[1] / "packaging" / "linux" / "install-deps.sh"
    )
    assert script_path.is_file(), f"{script_path} not found"
    content = script_path.read_text(encoding="utf-8")

    # Verify os-release detection
    assert "os-release" in content
    assert "ID" in content
    assert "ID_LIKE" in content

    # Verify supported distributions
    assert "fedora" in content
    assert "rhel" in content
    assert "centos" in content
    assert "ubuntu" in content
    assert "debian" in content

    # Verify package managers used
    assert "dnf" in content
    assert "apt-get" in content

    # Verify --runtime-only option
    assert "--runtime-only" in content

    # Verify Ubuntu package list includes rpm for cross-packaging RPMs and standard libgtk-3-0
    assert "rpm" in content
    assert "libgtk-3-0" in content
    assert "libgtk-3-0t64" not in content

    # Verify --detect-distro is processed before uname check so it can run cross-platform
    assert content.index("--detect-distro") < content.index("uname -s")

    # Verify Fedora packages
    assert "mpv-libs" in content
    assert "ffmpeg-free" in content
    assert "speech-dispatcher" in content
    assert "speech-dispatcher-libs" in content
    assert "speech-dispatcher-devel" in content
    assert "speech-dispatcher-espeak-ng" in content
    assert "at-spi2-core" in content
    assert "rpm-build" in content
    assert "xdg-utils" in content
    assert "xclip" in content
    assert "wl-clipboard" in content


def _find_bash() -> str | None:
    cmd = shutil.which("bash")
    if cmd:
        return cmd
    for candidate in [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


def test_detect_distro_os_release_parsing(tmp_path):
    samples = [
        ("ID=fedora\nVERSION_ID=43\n", "fedora"),
        ('ID="rhel"\nID_LIKE="fedora"\nVERSION_ID="9.4"\n', "fedora"),
        ('ID="centos"\nID_LIKE="rhel fedora"\n', "fedora"),
        ('ID="rocky"\nID_LIKE="rhel centos fedora"\n', "fedora"),
        ('ID="almalinux"\nID_LIKE="rhel centos fedora"\n', "fedora"),
        ("ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\n", "debian"),
        ("ID=debian\nVERSION_ID=12\n", "debian"),
        ('ID="linuxmint"\nID_LIKE="ubuntu debian"\n', "debian"),
        ('ID="pop"\nID_LIKE="ubuntu debian"\n', "debian"),
        ("ID=arch\n", "unknown"),
    ]

    for content, expected in samples:
        assert parse_os_release_distro(content) == expected

    # If bash is available, also test running install-deps.sh with mock os-release
    script_path = (
        Path(__file__).resolve().parents[1] / "packaging" / "linux" / "install-deps.sh"
    )
    bash_bin = _find_bash()
    if bash_bin:
        for content, expected in samples:
            if expected == "unknown":
                continue
            fake_os_release = tmp_path / "os-release"
            fake_os_release.write_text(content, encoding="utf-8")
            env = os.environ.copy()
            env["OS_RELEASE_FILE"] = str(fake_os_release)
            proc = subprocess.run(
                [bash_bin, str(script_path), "--detect-distro"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            assert proc.returncode == 0
            assert proc.stdout.strip() == expected


def test_installer_script_files_exist_and_delegate():
    repo_root = Path(__file__).resolve().parents[1]
    root_install = repo_root / "install.sh"
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    assert root_install.is_file(), "Root install.sh must exist"
    assert pkg_install.is_file(), "packaging/linux/install.sh must exist"

    root_text = root_install.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in root_text
    assert "packaging/linux/install.sh" in root_text

    pkg_text = pkg_install.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in pkg_text
    assert "--help" in pkg_text
    assert "--check-accessibility" in pkg_text
    assert "--source" in pkg_text
    assert "--package" in pkg_text
    assert "--dry-run" in pkg_text


def test_installer_cli_help_flag():
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"
    root_install = repo_root / "install.sh"

    for script in (pkg_install, root_install):
        proc = subprocess.run(
            [bash_bin, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert "HexPlayer" in proc.stdout
        assert "--help" in proc.stdout
        assert "--check-accessibility" in proc.stdout
        assert "--source" in proc.stdout
        assert "--package" in proc.stdout


def test_installer_cli_unknown_argument():
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    proc = subprocess.run(
        [bash_bin, str(pkg_install), "--unsupported-option"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "Unknown argument" in proc.stderr or "Unknown argument" in proc.stdout


def test_installer_fedora_package_detection_dry_run(tmp_path):
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    fake_os_release = tmp_path / "os-release"
    fake_os_release.write_text("ID=fedora\nVERSION_ID=43\n", encoding="utf-8")

    dummy_rpm = tmp_path / "HexPlayer-1.0.0-1.x86_64.rpm"
    dummy_rpm.write_text("dummy rpm content", encoding="utf-8")

    env = os.environ.copy()
    env["OS_RELEASE_FILE"] = str(fake_os_release)

    proc = subprocess.run(
        [bash_bin, str(pkg_install), "--package", str(dummy_rpm), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert "dnf install -y" in proc.stdout
    assert str(dummy_rpm).replace("\\", "/") in proc.stdout.replace("\\", "/")


def test_installer_debian_package_detection_dry_run(tmp_path):
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    fake_os_release = tmp_path / "os-release"
    fake_os_release.write_text(
        "ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\n", encoding="utf-8"
    )

    dummy_deb = tmp_path / "HexPlayer-1.0.0_amd64.deb"
    dummy_deb.write_text("dummy deb content", encoding="utf-8")

    env = os.environ.copy()
    env["OS_RELEASE_FILE"] = str(fake_os_release)

    proc = subprocess.run(
        [bash_bin, str(pkg_install), "--package", str(dummy_deb), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert "apt-get install -y --no-install-recommends" in proc.stdout
    assert str(dummy_deb).replace("\\", "/") in proc.stdout.replace("\\", "/")


def test_installer_source_mode_dry_run(tmp_path):
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    fake_os_release = tmp_path / "os-release"
    fake_os_release.write_text("ID=fedora\nVERSION_ID=43\n", encoding="utf-8")

    env = os.environ.copy()
    env["OS_RELEASE_FILE"] = str(fake_os_release)

    proc = subprocess.run(
        [bash_bin, str(pkg_install), "--source", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert "install-deps.sh" in proc.stdout


def test_installer_check_accessibility_flag():
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    proc = subprocess.run(
        [bash_bin, str(pkg_install), "--check-accessibility"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "Speech Dispatcher" in proc.stdout
    assert "AT-SPI2" in proc.stdout


def test_installer_auto_finds_dist_packages(tmp_path):
    bash_bin = _find_bash()
    if not bash_bin:
        return
    repo_root = Path(__file__).resolve().parents[1]
    pkg_install = repo_root / "packaging" / "linux" / "install.sh"

    # Test Fedora finding rpm in dist/
    fake_os_fedora = tmp_path / "os-release-fedora"
    fake_os_fedora.write_text("ID=fedora\nVERSION_ID=43\n", encoding="utf-8")

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    rpm_file = dist_dir / "HexPlayer-1.0.0-1.x86_64.rpm"
    rpm_file.write_text("dummy rpm", encoding="utf-8")

    env_fedora = os.environ.copy()
    env_fedora["OS_RELEASE_FILE"] = str(fake_os_fedora)

    proc_fedora = subprocess.run(
        [bash_bin, str(pkg_install), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env_fedora,
        check=False,
    )
    assert proc_fedora.returncode == 0
    assert "dnf install -y" in proc_fedora.stdout
    assert "HexPlayer-1.0.0-1.x86_64.rpm" in proc_fedora.stdout

    # Test Ubuntu finding deb in dist/
    rpm_file.unlink()
    fake_os_ubuntu = tmp_path / "os-release-ubuntu"
    fake_os_ubuntu.write_text("ID=ubuntu\nID_LIKE=debian\n", encoding="utf-8")
    deb_file = dist_dir / "HexPlayer-1.0.0_amd64.deb"
    deb_file.write_text("dummy deb", encoding="utf-8")

    env_ubuntu = os.environ.copy()
    env_ubuntu["OS_RELEASE_FILE"] = str(fake_os_ubuntu)

    proc_ubuntu = subprocess.run(
        [bash_bin, str(pkg_install), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env_ubuntu,
        check=False,
    )
    assert proc_ubuntu.returncode == 0
    assert "apt-get install -y --no-install-recommends" in proc_ubuntu.stdout
    assert "HexPlayer-1.0.0_amd64.deb" in proc_ubuntu.stdout
