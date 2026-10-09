"""Filter-chain tests for ``MpvMediaPlayer.apply_equalizer``.

These assert the FFmpeg ``af`` string the backend builds from a preamp and the
15 band gains, in particular that the extreme bands render as shelving filters
(low shelf at 25 Hz, high shelf at 16 kHz) while the middle bands stay peaking.
The player is built with ``object.__new__`` so no ``libmpv-2.dll`` is loaded.
"""

import threading

from media_player.mpv_backend import MpvMediaPlayer


def _build_af(preamp, bands):
    """Return the ``af`` value apply_equalizer would push to MPV."""
    player = object.__new__(MpvMediaPlayer)
    player._lock = threading.RLock()
    player._closed = False
    captured = {}
    player._set_property_string = lambda name, value: captured.__setitem__(name, value)

    player.apply_equalizer(preamp, bands)
    return captured.get("af")


def test_lowest_band_is_a_low_shelf():
    bands = [6.0] + [0.0] * 14
    af = _build_af(0.0, bands)
    assert af == "lavfi=[lowshelf=f=25:t=q:w=0.7:g=6]"


def test_highest_band_is_a_high_shelf():
    bands = [0.0] * 14 + [6.0]
    af = _build_af(0.0, bands)
    assert af == "lavfi=[highshelf=f=16000:t=q:w=0.7:g=6]"


def test_middle_bands_stay_peaking():
    bands = [0.0] * 15
    bands[8] = -4.0  # 1 kHz band
    af = _build_af(0.0, bands)
    assert af == "lavfi=[equalizer=f=1000:t=q:w=2:g=-4]"


def test_full_chain_orders_preamp_then_shelves_and_peaks():
    bands = [0.0] * 15
    bands[0] = 8.0  # low shelf
    bands[1] = 3.0  # peaking (40 Hz)
    bands[14] = 5.0  # high shelf
    af = _build_af(-6.0, bands)
    assert af == (
        "lavfi=[volume=-6dB,"
        "lowshelf=f=25:t=q:w=0.7:g=8,"
        "equalizer=f=40:t=q:w=2:g=3,"
        "highshelf=f=16000:t=q:w=0.7:g=5]"
    )


def test_flat_settings_clear_the_filter_chain():
    af = _build_af(0.0, [0.0] * 15)
    assert af == ""


def test_closed_player_does_not_push_a_filter():
    player = object.__new__(MpvMediaPlayer)
    player._lock = threading.RLock()
    player._closed = True
    calls = []
    player._set_property_string = lambda name, value: calls.append((name, value))

    player.apply_equalizer(0.0, [6.0] * 15)
    assert calls == []
