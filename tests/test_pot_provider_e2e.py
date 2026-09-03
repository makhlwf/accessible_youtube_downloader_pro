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
    # Check scratch fallback
    scratch_exe = r"C:\Users\altrh\.gemini\antigravity-cli\brain\624f85b2-d536-4465-be35-f904a5909e38\scratch\bgutil-pot.exe"
    scratch_plugins = r"C:\Users\altrh\.gemini\antigravity-cli\brain\624f85b2-d536-4465-be35-f904a5909e38\scratch\plugin\yt_dlp_plugins"
    if os.path.isfile(scratch_exe):
        return scratch_exe, scratch_plugins
    return None, None


SRC_EXE, SRC_PLUGINS = _find_test_binaries()


@pytest.mark.skipif(
    SRC_EXE is None or not os.path.exists(SRC_EXE),
    reason="bgutil-pot binary not found via POT_TEST_DIR, appdata, or scratch",
)
def test_e2e_pot_provider_lifecycle_and_live_ytdlp():
    # Setup test binary and plugins in appdata location if missing
    os.makedirs(paths.pot_provider_dir, exist_ok=True)
    if not os.path.exists(paths.pot_provider_exe) and SRC_EXE:
        shutil.copy2(SRC_EXE, paths.pot_provider_exe)

    plugins_target = os.path.join(paths.pot_provider_plugins_dir, "yt_dlp_plugins")
    if (
        not os.path.exists(plugins_target)
        and SRC_PLUGINS
        and os.path.exists(SRC_PLUGINS)
    ):
        os.makedirs(paths.pot_provider_plugins_dir, exist_ok=True)
        shutil.copytree(SRC_PLUGINS, plugins_target, dirs_exist_ok=True)

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
        assert "Rick Astley" in info.get(
            "title", ""
        ) or "Never Gonna Give You Up" in info.get("title", "")
    finally:
        # 4. Stop service and verify clean shutdown
        pot_service.stop()
        assert not pot_service.is_running()
        assert not pot_service.is_healthy()
