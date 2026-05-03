from media_player.equalizer import EqualizerService


def test_equalizer_init():
    eq = EqualizerService()
    assert eq.equalizer is not None


def test_preamp_setting():
    eq = EqualizerService()
    eq.set_preamp(5.0)
    # VLC doesn't expose a simple getter for current preamp easily,
    # but we can verify our internal state
    assert eq.preamp == 5.0
