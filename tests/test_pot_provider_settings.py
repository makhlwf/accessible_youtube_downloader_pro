import os

import paths
from settings_handler import defaults


def test_pot_provider_paths():
    assert paths.pot_provider_dir.endswith("pot_provider")
    assert paths.pot_provider_exe == os.path.join(
        paths.pot_provider_dir, "bgutil-pot.exe"
    )
    assert paths.pot_provider_plugins_dir == os.path.join(
        paths.pot_provider_dir, "plugins"
    )
    assert paths.pot_provider_version_file == os.path.join(
        paths.pot_provider_dir, "version.json"
    )


def test_pot_provider_settings_defaults():
    assert "pot_provider_enabled" in defaults
    assert defaults["pot_provider_enabled"] is True
    assert "pot_provider_port" in defaults
    assert defaults["pot_provider_port"] == 4416
