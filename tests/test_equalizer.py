import pytest
from unittest.mock import MagicMock, patch
from media_player.equalizer import EqualizerService


def test_equalizer_init():
    eq = EqualizerService()
    assert eq.equalizer is not None


def test_preamp_setting():
    eq = EqualizerService()
    eq.set_preamp(5.0)
    assert eq.preamp == 5.0
    with pytest.raises(ValueError, match="Preamp value out of range"):
        eq.set_preamp(30.0)


def test_set_band_validation():
    eq = EqualizerService()
    # Test valid band index
    eq.set_band(0, 5.0)

    # Test invalid band index
    with pytest.raises(ValueError, match="Index out of range"):
        eq.set_band(-1, 0.0)
    with pytest.raises(ValueError, match="Index out of range"):
        eq.set_band(20, 0.0)

    # Test invalid gain value
    with pytest.raises(ValueError, match="Gain value out of range"):
        eq.set_band(0, 30.0)
    with pytest.raises(ValueError, match="Gain value out of range"):
        eq.set_band(0, -30.0)


def test_apply_to_player_with_mock():
    eq = EqualizerService()
    mock_player = MagicMock()
    eq.apply_to_player(mock_player)

    mock_player.set_equalizer.assert_called_once_with(eq.equalizer)


def test_get_band():
    eq = EqualizerService()
    eq.set_band(0, 5.0)
    assert eq.get_band(0) == 5.0


def test_get_preamp():
    eq = EqualizerService()
    eq.set_preamp(10.0)
    assert eq.get_preamp() == 10.0


def test_presets():
    eq = EqualizerService()
    eq.apply_preset("Rock")
    # Verify some band values for Rock (index 0 is 8.0)
    assert eq.get_band(0) == 8.0


def test_presets_updates_preamp():
    eq = EqualizerService()
    # Ensure starting preamp is 0.0
    eq.set_preamp(0.0)
    # Applying "Rock" should update preamp
    eq.apply_preset("Rock")
    # We will define Rock's preamp as 5.0 in our implementation
    assert eq.preamp == 5.0


def test_load_settings():
    with patch("settings_handler.config_get") as mock_get:

        def side_effect(key):
            if key == "eq_bands":
                return "1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0"
            if key == "eq_preamp":
                return 5.0
            return None

        mock_get.side_effect = side_effect

        eq = EqualizerService()
        eq.load_settings()
        assert eq.preamp == 5.0
        assert eq.get_band(0) == 1.0
        assert eq.get_band(9) == 10.0


def test_save_settings():
    with patch("settings_handler.config_set") as mock_set:
        eq = EqualizerService()
        eq.set_preamp(3.0)
        eq.set_band(0, 1.0)
        eq.set_band(1, 2.0)
        # ... other bands 0.0
        eq.save_settings()

        mock_set.assert_any_call("eq_preamp", 3.0)
        # The expected bands string for 1.0, 2.0, then 8 zeros
        expected_bands = "1.0,2.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0"
        mock_set.assert_any_call("eq_bands", expected_bands)


def test_reset():
    eq = EqualizerService()
    eq.set_preamp(5.0)
    eq.set_band(0, 5.0)
    eq.reset()
    assert eq.preamp == 0.0
    assert eq.get_band(0) == 0.0
