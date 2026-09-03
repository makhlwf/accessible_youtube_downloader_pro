import io
import json
import sys
import zipfile
from unittest.mock import MagicMock, patch

from pot_provider_service import PotProviderService, pot_service


def test_pot_service_singleton():
    assert isinstance(pot_service, PotProviderService)


def test_service_get_port_validation(monkeypatch):
    service = PotProviderService()

    # Valid int
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: 8080)
    assert service.get_port() == 8080

    # Valid string
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: "5000")
    assert service.get_port() == 5000

    # Out of range low / high
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: 0)
    assert service.get_port() == 4416
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: 70000)
    assert service.get_port() == 4416

    # Malformed / None
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: "invalid")
    assert service.get_port() == 4416
    monkeypatch.setattr("pot_provider_service.config_get", lambda k: None)
    assert service.get_port() == 4416


def test_service_plugin_sys_path(tmp_path, monkeypatch):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True)
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(plugins_dir))

    service = PotProviderService()
    service.initialize()
    assert str(plugins_dir) in sys.path


def test_service_is_installed(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    plugins = tmp_path / "plugins"
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(plugins))

    service = PotProviderService()
    assert not service.is_installed()

    exe.write_text("dummy")
    assert not service.is_installed()

    plugins.mkdir()
    assert service.is_installed()


def test_service_has_binary(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))

    service = PotProviderService()
    assert not service.has_binary()

    exe.write_text("dummy")
    assert service.has_binary()


def test_service_health_check():
    service = PotProviderService()
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok", "version": "0.8.1"}'
        mock_url.return_value.__enter__.return_value = mock_resp

        assert service.is_healthy()


def test_service_health_check_failure():
    service = PotProviderService()
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        assert not service.is_healthy()


def test_service_is_available(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    exe.write_text("dummy")
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(plugins))

    service = PotProviderService()
    with patch.object(service, "is_healthy", return_value=False):
        assert not service.is_available()

    with patch.object(service, "is_healthy", return_value=True):
        assert service.is_available()


def test_service_start_stop(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    exe.write_text("dummy")
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))

    service = PotProviderService()
    with (
        patch("subprocess.Popen") as mock_popen,
        patch.object(service, "is_healthy", side_effect=[False, True]),
    ):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout = ["Started server\n"]
        mock_proc.stderr = []
        mock_popen.return_value = mock_proc

        started = service.start()
        assert started is True
        assert service.is_running()

        service.stop()
        mock_proc.kill.assert_called_once()
        assert not service.is_running()


def test_service_start_timeout_stops_process(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    exe.write_text("dummy")
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))

    service = PotProviderService()
    with (
        patch("subprocess.Popen") as mock_popen,
        patch.object(service, "is_healthy", return_value=False),
        patch.object(service, "stop") as mock_stop,
        patch("time.time", side_effect=[0, 0.5, 3.5, 4.0]),
        patch("time.sleep"),
    ):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout = []
        mock_proc.stderr = []
        mock_popen.return_value = mock_proc

        started = service.start()
        assert started is False
        mock_stop.assert_called_once()


def test_service_start_does_not_spawn_duplicate_process(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    exe.write_text("dummy")
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))

    service = PotProviderService()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    service.process = mock_proc

    with (
        patch("subprocess.Popen") as mock_popen,
        patch.object(service, "is_healthy", side_effect=[False, True]),
    ):
        result = service.start()
        assert result is True
        mock_popen.assert_not_called()

    # Also verify when already healthy
    with (
        patch("subprocess.Popen") as mock_popen,
        patch.object(service, "is_healthy", return_value=True),
    ):
        result = service.start()
        assert result is True
        mock_popen.assert_not_called()


def test_service_stop_safe_logger_exception():
    service = PotProviderService()
    mock_proc = MagicMock()
    service.process = mock_proc
    with patch(
        "pot_provider_service.logger.info",
        side_effect=ValueError("I/O operation on closed file"),
    ):
        service.stop()
        assert service.process is None
        mock_proc.kill.assert_called_once()


def test_service_ensure_started(tmp_path, monkeypatch):
    exe = tmp_path / "bgutil-pot.exe"
    exe.write_text("dummy")
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(plugins))

    service = PotProviderService()

    # Disabled in settings
    with patch(
        "pot_provider_service.config_get",
        side_effect=lambda k: False if k == "pot_provider_enabled" else None,
    ):
        assert service.ensure_started() is False

    # Enabled in settings, starts successfully
    with (
        patch(
            "pot_provider_service.config_get",
            side_effect=lambda k: True if k == "pot_provider_enabled" else None,
        ),
        patch.object(service, "start", return_value=True) as mock_start,
    ):
        assert service.ensure_started() is True
        mock_start.assert_called_once()


def test_service_get_installed_version(tmp_path, monkeypatch):
    vfile = tmp_path / "version.json"
    exe = tmp_path / "bgutil-pot.exe"
    monkeypatch.setattr("paths.pot_provider_version_file", str(vfile))
    monkeypatch.setattr("paths.pot_provider_exe", str(exe))

    service = PotProviderService()
    assert service.get_installed_version() is None

    # From version file
    vfile.write_text(json.dumps({"version": "v0.8.1"}))
    assert service.get_installed_version() == "v0.8.1"

    # From binary fallback - without v prefix
    vfile.unlink()
    exe.write_text("dummy")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="bgutil-pot 0.8.1\n")
        assert service.get_installed_version() == "v0.8.1"

    # From binary fallback - already with v prefix
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="bgutil-pot v0.8.1\n")
        assert service.get_installed_version() == "v0.8.1"


def test_service_download_and_install(tmp_path, monkeypatch):
    pdir = tmp_path / "pot_provider"
    pexe = pdir / "bgutil-pot.exe"
    pplugins = pdir / "plugins"
    pvfile = pdir / "version.json"

    monkeypatch.setattr("paths.pot_provider_dir", str(pdir))
    monkeypatch.setattr("paths.pot_provider_exe", str(pexe))
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(pplugins))
    monkeypatch.setattr("paths.pot_provider_version_file", str(pvfile))

    service = PotProviderService()

    mock_release_resp = MagicMock()
    mock_release_resp.status_code = 200
    mock_release_resp.json.return_value = {
        "tag_name": "v0.8.1",
        "assets": [
            {
                "name": "bgutil-pot-windows-x86_64.exe",
                "browser_download_url": "https://example.com/bgutil-pot.exe",
            },
            {
                "name": "bgutil-ytdlp-pot-provider-rs.zip",
                "browser_download_url": "https://example.com/plugins.zip",
            },
        ],
    }

    zip_bytes_io = io.BytesIO()
    with zipfile.ZipFile(zip_bytes_io, "w") as zf:
        zf.writestr("test_plugin.py", "print('plugin')")
    zip_bytes = zip_bytes_io.getvalue()

    def fake_update_dialog(parent, url, dest_path, title, is_zip=False):
        if dest_path.endswith(".exe.download"):
            with open(dest_path, "wb") as f:
                f.write(b"dummy_exe_content")
        elif dest_path.endswith(".zip.download"):
            with open(dest_path, "wb") as f:
                f.write(zip_bytes)

    with (
        patch("requests.get", return_value=mock_release_resp) as mock_get,
        patch("gui.update_dialog.UpdateDialog", side_effect=fake_update_dialog),
        patch.object(service, "start", return_value=True),
    ):
        success = service.download_and_install()
        assert success is True
        assert pexe.exists()
        assert (pplugins / "test_plugin.py").exists()
        assert pvfile.exists()
        assert json.loads(pvfile.read_text())["version"] == "v0.8.1"
        mock_get.assert_called_once()
        assert mock_get.call_args[1]["headers"]["User-Agent"] == "HexPlayer"


def test_service_download_and_install_replace_failure(tmp_path, monkeypatch):
    pdir = tmp_path / "pot_provider"
    pexe = pdir / "bgutil-pot.exe"
    pplugins = pdir / "plugins"
    pvfile = pdir / "version.json"

    monkeypatch.setattr("paths.pot_provider_dir", str(pdir))
    monkeypatch.setattr("paths.pot_provider_exe", str(pexe))
    monkeypatch.setattr("paths.pot_provider_plugins_dir", str(pplugins))
    monkeypatch.setattr("paths.pot_provider_version_file", str(pvfile))

    service = PotProviderService()

    mock_release_resp = MagicMock()
    mock_release_resp.status_code = 200
    mock_release_resp.json.return_value = {
        "tag_name": "v0.8.1",
        "assets": [
            {
                "name": "bgutil-pot-windows-x86_64.exe",
                "browser_download_url": "https://example.com/bgutil-pot.exe",
            },
            {
                "name": "bgutil-ytdlp-pot-provider-rs.zip",
                "browser_download_url": "https://example.com/plugins.zip",
            },
        ],
    }

    zip_bytes_io = io.BytesIO()
    with zipfile.ZipFile(zip_bytes_io, "w") as zf:
        zf.writestr("test_plugin.py", "print('plugin')")
    zip_bytes = zip_bytes_io.getvalue()

    # Pre-populate existing files to verify rollback
    pdir.mkdir(parents=True, exist_ok=True)
    pexe.write_text("old_exe")
    pplugins.mkdir(parents=True, exist_ok=True)
    (pplugins / "old_plugin.py").write_text("old_plugin")

    def fake_update_dialog(parent, url, dest_path, title, is_zip=False):
        if dest_path.endswith(".exe.download"):
            with open(dest_path, "wb") as f:
                f.write(b"new_exe")
        elif dest_path.endswith(".zip.download"):
            with open(dest_path, "wb") as f:
                f.write(zip_bytes)

    with (
        patch("requests.get", return_value=mock_release_resp),
        patch("gui.update_dialog.UpdateDialog", side_effect=fake_update_dialog),
        patch("os.replace", side_effect=OSError("Permission denied")),
    ):
        success = service.download_and_install()
        assert success is False
        # Old exe and plugins should be preserved
        assert pexe.read_text() == "old_exe"
        assert (pplugins / "old_plugin.py").exists()
