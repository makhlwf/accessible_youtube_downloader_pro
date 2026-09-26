"""Regression tests for the mpv ``loadfile`` command signature.

mpv 0.38 (libmpv client API 2.3) inserted an ``<index>`` argument into the
``loadfile`` command *before* the options map. HexPlayer bundles a modern mpv
on Windows but loads the *system* libmpv on Linux, which on Ubuntu 24.04 is
mpv 0.37 (API 2.2). Sending the newer 5-argument shape to that build makes it
parse ``"-1"`` as the options string and reject the trailing map with
"invalid parameter", aborting all playback. ``_load_current`` must therefore
pick the command shape from the runtime API version.
"""

import types

from media_player import mpv_backend


def _make_player(api_version, options):
    """Build an MpvMediaPlayer without touching a real libmpv / event thread."""
    player = object.__new__(mpv_backend.MpvMediaPlayer)
    player._lib = types.SimpleNamespace(
        mpv_command_node=lambda *args: 0,
        mpv_error_string=lambda code: b"error",
    )
    player._handle = 1
    player._api_version = api_version
    player._loaded = True
    player._state = mpv_backend.State.NothingSpecial
    player._current_media = mpv_backend.MpvMedia("https://host/video.m4v", options)
    return player


def _capture_loadfile(player, monkeypatch):
    """Run _load_current and decode the node command it hands to libmpv."""
    captured = {}
    real_byref = mpv_backend.ctypes.byref

    def spy_byref(obj, *args):
        captured["root"] = obj  # keeps the node graph alive via ctypes _objects
        return real_byref(obj, *args)

    monkeypatch.setattr(mpv_backend.ctypes, "byref", spy_byref)
    player._load_current()
    return mpv_backend._parse_node(captured["root"])


DASH_OPTIONS = [":http-user-agent=HexPlayer/1.0", ":input-slave=https://host/audio.m4a"]
EXPECTED_MAP = {"user-agent": "HexPlayer/1.0", "audio-file": "https://host/audio.m4a"}


def test_legacy_shape_on_mpv_0_37(monkeypatch):
    # API 2.2 == mpv 0.37 (Ubuntu 24.04). No <index>; options in slot 3.
    player = _make_player(0x00020002, DASH_OPTIONS)
    decoded = _capture_loadfile(player, monkeypatch)
    assert decoded[:3] == ["loadfile", "https://host/video.m4v", "replace"]
    assert len(decoded) == 4
    assert decoded[3] == EXPECTED_MAP


def test_index_shape_on_mpv_0_38_plus(monkeypatch):
    # API 2.3 == mpv 0.38. <index> is inserted before the options map.
    player = _make_player(0x00020003, DASH_OPTIONS)
    decoded = _capture_loadfile(player, monkeypatch)
    assert decoded[:3] == ["loadfile", "https://host/video.m4v", "replace"]
    assert len(decoded) == 5
    assert decoded[3] == "-1"
    assert decoded[4] == EXPECTED_MAP


def test_modern_bundled_mpv_uses_index_shape(monkeypatch):
    # The Windows-bundled build reports API 2.5 (mpv 0.41): keep the index shape.
    player = _make_player(0x00020005, [])
    decoded = _capture_loadfile(player, monkeypatch)
    assert len(decoded) == 5
    assert decoded[3] == "-1"
    assert decoded[4] == {}


def test_threshold_constant_matches_mpv_0_38():
    assert mpv_backend.MPV_LOADFILE_INDEX_API == 0x00020003
