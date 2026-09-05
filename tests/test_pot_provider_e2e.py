import os
import shutil

import pytest

import paths
import utils
from pot_provider_service import pot_service


def _find_test_binaries():
    # Check explicit environment variable
    env_dir = os.environ.get("POT_TEST_DIR")
    if env_dir and os.path.isfile(os.path.join(env_dir, "bgutil-pot.exe")):
        plugin_path = os.path.join(env_dir, "plugin", "yt_dlp_plugins")
        if not os.path.isdir(plugin_path):
            plugin_path = os.path.join(env_dir, "yt_dlp_plugins")
        return os.path.join(env_dir, "bgutil-pot.exe"), plugin_path

    # Check installed in appdata
    if os.path.isfile(paths.pot_provider_exe) and os.path.isdir(
        paths.pot_provider_plugins_dir
    ):
        return paths.pot_provider_exe, os.path.join(
            paths.pot_provider_plugins_dir, "yt_dlp_plugins"
        )

    return None, None


SRC_EXE, SRC_PLUGINS = _find_test_binaries()


@pytest.mark.skipif(
    SRC_EXE is None or not os.path.exists(SRC_EXE),
    reason="bgutil-pot binary not found via POT_TEST_DIR or AppData",
)
def test_e2e_pot_provider_lifecycle_and_live_ytdlp(tmp_path, monkeypatch):
    # Isolate test binary and plugins under tmp_path so user AppData is not modified
    test_dir = tmp_path / "pot_provider"
    test_exe = test_dir / "bgutil-pot.exe"
    test_plugins = test_dir / "plugins"
    test_vfile = test_dir / "version.json"

    test_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_EXE, str(test_exe))

    plugins_target = test_plugins / "yt_dlp_plugins"
    if SRC_PLUGINS and os.path.exists(SRC_PLUGINS):
        test_plugins.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SRC_PLUGINS, str(plugins_target), dirs_exist_ok=True)

    monkeypatch.setattr(paths, "pot_provider_dir", str(test_dir))
    monkeypatch.setattr(paths, "pot_provider_exe", str(test_exe))
    monkeypatch.setattr(paths, "pot_provider_plugins_dir", str(test_plugins))
    monkeypatch.setattr(paths, "pot_provider_version_file", str(test_vfile))

    # Isolate configuration so user settings.ini cannot disable provider during test
    monkeypatch.setattr(
        "utils.config_get",
        lambda k, default=None: (
            True
            if k == "pot_provider_enabled"
            else (4499 if k == "pot_provider_port" else default)
        ),
    )
    monkeypatch.setattr(
        "pot_provider_service.config_get",
        lambda k, default=None: (
            True
            if k == "pot_provider_enabled"
            else (4499 if k == "pot_provider_port" else default)
        ),
    )

    pot_service._initialized = False

    try:
        # 1. Start service
        started = pot_service.start()
        assert started is True
        assert pot_service.is_healthy() is True

        # 2. Verify yt-dlp instance creation and extractor args
        ydl = utils.get_ydl_instance()
        assert ydl is not None
        extractor_args = ydl.params.get("extractor_args", {})
        assert "youtubepot-bgutilhttp" in extractor_args

        # 3. Live extraction with yt-dlp (verifies real botguard token acquisition)
        info = ydl.extract_info(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False
        )
        assert info is not None
        assert info.get("id") == "dQw4w9WgXcQ"
        assert info.get("title")
    finally:
        # 4. Stop service and verify clean shutdown
        pot_service.stop()
        assert not pot_service.is_running()
        assert not pot_service.is_healthy()
