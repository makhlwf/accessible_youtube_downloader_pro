import os
from settings_handler import config_get, config_set, defaults, config_initialization
from paths import settings_path


def test_eq_settings():
    # Ensure fresh settings
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))
    config_initialization()

    # Verify defaults
    assert config_get("eq_enabled") == defaults["eq_enabled"]
    assert config_get("eq_preamp") == defaults["eq_preamp"]
    assert config_get("eq_bands") == defaults["eq_bands"]
    assert config_get("eq_preset") == defaults["eq_preset"]

    # Test setting values
    config_set("eq_enabled", True)
    assert config_get("eq_enabled") is True

    # Cleanup
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))
