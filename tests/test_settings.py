import pytest
import os
from unittest.mock import patch, mock_open
import settings_handler

def test_string_to_bool():
    assert settings_handler.string_to_bool("True") is True
    assert settings_handler.string_to_bool("False") is False
    assert settings_handler.string_to_bool("123") == 123
    assert settings_handler.string_to_bool("1.5") == 1.5
    assert settings_handler.string_to_bool("hello") == "hello"

def test_config_get_default():
    # Test getting a default value when not in cache
    with patch("settings_handler._cache", {}):
        # We need to mock config_set or avoid it writing to disk
        with patch("settings_handler.config_set") as mock_set:
            val = settings_handler.config_get("seek")
            assert val == 5

def test_config_set_and_get():
    # Test setting and then getting a value
    mock_conf = "[settings]\nseek = 10\n"
    with patch("builtins.open", mock_open(read_data=mock_conf)) as m:
        with patch("os.path.exists", return_value=True):
            settings_handler.config_set("seek", 10)
            assert settings_handler.config_get("seek") == 10
            # Verify file was written
            m.assert_called_with(os.path.join(settings_handler.settings_path, "settings.ini"), "w", encoding="utf-8")
