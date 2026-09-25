"""Load equalizer presets from the bundled ``eq_presets`` data directory.

Each preset lives in its own JSON file so presets can be added, edited, or
removed without touching Python code. A file looks like::

    {
      "key": "Rock",
      "preamp": 5.0,
      "bands": [8.0, 8.0, 8.0, 7.0, 5.0, -1.0, -6.0, -8.0, -3.0, 0.0, 2.0, 5.0, 8.0, 10.0, 11.0]
    }

``key`` is the stable identifier written to the settings file, so it must not
change once shipped; only the translated label (see ``gui/equalizer_dialog``)
is user-facing. Presets are listed alphabetically by ``key`` in the dropdown,
so no ordering field is stored. ``bands`` holds one gain (dB) per band across
the 15-band graphic-equalizer grid (see ``BAND_COUNT``).

Everything here is defensive on purpose: a hand-edited or corrupt preset file
must never crash the player. Bad files are skipped, out-of-range gains are
clamped, and if nothing usable is found we still return a flat preset.
"""

import json
import logging
import os
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

PRESET_DIR_NAME = "eq_presets"
BAND_COUNT = 15
GAIN_MIN = -20.0
GAIN_MAX = 20.0

# Always-available fallback so the equalizer works even with no data files.
FLAT_PRESET: dict[str, Any] = {"preamp": 0.0, "bands": [0.0] * BAND_COUNT}


def _clamp(value: float) -> float:
    return max(GAIN_MIN, min(GAIN_MAX, value))


def presets_dir() -> str:
    """Absolute path to the preset directory (dev tree and frozen build)."""
    from paths import get_bundled_data_path

    return os.path.join(get_bundled_data_path(), PRESET_DIR_NAME)


def _normalize_bands(raw: Any) -> list[float]:
    """Coerce ``raw`` into exactly ``BAND_COUNT`` clamped float gains."""
    if not isinstance(raw, (list, tuple)):
        raise TypeError("'bands' must be a list")
    bands = [_clamp(float(value)) for value in raw[:BAND_COUNT]]
    # Pad short definitions with 0.0 so downstream code always sees 10 bands.
    bands.extend([0.0] * (BAND_COUNT - len(bands)))
    return bands


def _parse_preset(raw: Any) -> tuple[str, dict[str, Any]]:
    """Validate one decoded preset document.

    Returns ``(key, preset)`` or raises ``ValueError`` if unusable.
    """
    if not isinstance(raw, dict):
        raise TypeError("preset must be a JSON object")

    key = raw.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("preset is missing a non-empty 'key'")
    key = key.strip()

    preamp = _clamp(float(raw.get("preamp", 0.0)))
    bands = _normalize_bands(raw.get("bands", []))
    return key, {"preamp": preamp, "bands": bands}


def load_presets(directory: str | None = None) -> OrderedDict[str, dict[str, Any]]:
    """Return an ordered ``{key: {"preamp", "bands"}}`` mapping.

    Presets are ordered alphabetically by ``key`` (case-insensitive). "Flat" is
    guaranteed to be present even if its file is missing, so the dropdown and
    reset behaviour always have a sane default.
    """
    directory = directory or presets_dir()
    collected: dict[str, dict[str, Any]] = {}

    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        logger.warning("Equalizer preset directory not found: %s", directory)
        entries = []

    for filename in entries:
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(directory, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            key, preset = _parse_preset(raw)
        except OSError, TypeError, ValueError, json.JSONDecodeError:
            logger.exception("Skipping invalid equalizer preset: %s", path)
            continue
        if key in collected:
            logger.warning("Duplicate equalizer preset key %r in %s", key, path)
            continue
        collected[key] = preset

    # "Flat" must always exist as the neutral reset default.
    if "Flat" not in collected:
        collected["Flat"] = {"preamp": 0.0, "bands": [0.0] * BAND_COUNT}

    presets: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for key in sorted(collected, key=str.casefold):
        presets[key] = collected[key]

    return presets
