import json

from media_player import preset_library
from media_player.equalizer import EqualizerService


def _write(directory, filename, payload):
    path = directory / filename
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_shipped_presets_load_and_are_valid():
    presets = preset_library.load_presets()
    assert len(presets) >= 40
    # Presets are listed alphabetically (case-insensitive) by key.
    keys = list(presets)
    assert keys == sorted(keys, key=str.casefold)
    assert "Flat" in presets
    for name, preset in presets.items():
        assert len(preset["bands"]) == preset_library.BAND_COUNT, name
        assert preset_library.GAIN_MIN <= preset["preamp"] <= preset_library.GAIN_MAX
        for gain in preset["bands"]:
            assert preset_library.GAIN_MIN <= gain <= preset_library.GAIN_MAX, name


def test_equalizer_service_uses_loaded_presets():
    # The service catalogue is exactly what the loader produced.
    assert EqualizerService.PRESETS == preset_library.load_presets()


def test_presets_ordered_alphabetically(tmp_path):
    _write(tmp_path, "b.json", {"key": "bravo", "preamp": 0.0, "bands": []})
    _write(tmp_path, "a.json", {"key": "Alpha", "preamp": 0.0, "bands": []})
    _write(tmp_path, "f.json", {"key": "Flat", "preamp": 0.0, "bands": []})

    presets = preset_library.load_presets(str(tmp_path))
    # Case-insensitive alphabetical: Alpha, bravo, Flat.
    assert list(presets) == ["Alpha", "bravo", "Flat"]


def test_short_bands_are_padded_and_gains_clamped(tmp_path):
    _write(
        tmp_path,
        "boom.json",
        {"key": "Boom", "order": 10, "preamp": 99.0, "bands": [50.0, -99.0, 3.0]},
    )
    presets = preset_library.load_presets(str(tmp_path))
    boom = presets["Boom"]
    assert len(boom["bands"]) == preset_library.BAND_COUNT
    assert boom["preamp"] == preset_library.GAIN_MAX
    assert boom["bands"][0] == preset_library.GAIN_MAX
    assert boom["bands"][1] == preset_library.GAIN_MIN
    assert boom["bands"][2] == 3.0
    assert boom["bands"][3] == 0.0  # padded


def test_invalid_files_are_skipped(tmp_path):
    _write(
        tmp_path, "good.json", {"key": "Good", "order": 10, "preamp": 1.0, "bands": []}
    )
    _write(tmp_path, "broken.json", "{ this is not json ")
    _write(tmp_path, "nokey.json", {"order": 5, "preamp": 0.0, "bands": []})
    _write(tmp_path, "notes.txt", "ignored, not a preset")

    presets = preset_library.load_presets(str(tmp_path))
    # Good plus the injected Flat fallback, nothing else.
    assert set(presets) == {"Flat", "Good"}


def test_duplicate_keys_keep_first(tmp_path):
    _write(
        tmp_path,
        "1_first.json",
        {"key": "Dup", "order": 10, "preamp": 1.0, "bands": []},
    )
    _write(
        tmp_path,
        "2_second.json",
        {"key": "Dup", "order": 20, "preamp": 5.0, "bands": []},
    )

    presets = preset_library.load_presets(str(tmp_path))
    assert presets["Dup"]["preamp"] == 1.0


def test_missing_directory_falls_back_to_flat(tmp_path):
    presets = preset_library.load_presets(str(tmp_path / "does_not_exist"))
    assert list(presets) == ["Flat"]
    assert presets["Flat"] == {
        "preamp": 0.0,
        "bands": [0.0] * preset_library.BAND_COUNT,
    }


def test_load_settings_clamps_out_of_range_bands():
    from unittest.mock import patch

    # A full 15-value string so it is treated as the current-format curve.
    bands = "99.0,-99.0,bogus,2.0," + ",".join(["0.0"] * 11)
    stored = {"eq_preamp": 3.0, "eq_bands": bands}
    with patch("settings_handler.config_get", side_effect=stored.get):
        eq = EqualizerService()
        eq.load_settings()

    assert eq.get_preamp() == 3.0
    assert eq.get_band(0) == preset_library.GAIN_MAX
    assert eq.get_band(1) == preset_library.GAIN_MIN
    # "bogus" token is skipped -> band 2 keeps its default 0.0
    assert eq.get_band(2) == 0.0
    assert eq.get_band(3) == 2.0


def test_load_settings_migrates_legacy_band_count_from_preset():
    from unittest.mock import patch

    # A pre-15-band settings string (10 values) can't map onto the new grid,
    # so the saved preset's bands are used instead.
    stored = {
        "eq_preamp": 0.0,
        "eq_bands": ",".join(["1.0"] * 10),
        "eq_preset": "Rock",
    }
    with patch("settings_handler.config_get", side_effect=stored.get):
        eq = EqualizerService()
        eq.load_settings()

    assert [eq.get_band(i) for i in range(preset_library.BAND_COUNT)] == (
        EqualizerService.PRESETS["Rock"]["bands"]
    )
