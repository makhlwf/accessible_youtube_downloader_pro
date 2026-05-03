import pytest
from unittest.mock import MagicMock
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
