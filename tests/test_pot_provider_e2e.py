import os
import shutil

import pytest

import paths
import utils
from pot_provider_service import pot_service

SCRATCH_DIR = r"C:\Users\altrh\.gemini\antigravity-cli\brain\624f85b2-d536-4465-be35-f904a5909e38\scratch"
SCRATCH_EXE = os.path.join(SCRATCH_DIR, "bgutil-pot.exe")
SCRATCH_PLUGINS = os.path.join(SCRATCH_DIR, "plugin", "yt_dlp_plugins")


@pytest.mark.skipif(
    not os.path.exists(SCRATCH_EXE), reason="Scratch bgutil-pot binary not found"
)
def test_e2e_pot_provider_lifecycle_and_live_ytdlp():
    # Setup test binary and plugins in appdata location if missing
    os.makedirs(paths.pot_provider_dir, exist_ok=True)
    if not os.path.exists(paths.pot_provider_exe):
        shutil.copy2(SCRATCH_EXE, paths.pot_provider_exe)

    plugins_target = os.path.join(paths.pot_provider_plugins_dir, "yt_dlp_plugins")
    if not os.path.exists(plugins_target):
        os.makedirs(paths.pot_provider_plugins_dir, exist_ok=True)
        shutil.copytree(SCRATCH_PLUGINS, plugins_target, dirs_exist_ok=True)

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
