"""Tests for the YouTube Music settings tab."""

from unittest.mock import patch

import wx

import settings_handler
from gui import settings_dialog

settings_handler.config_initialization()


def _dialog():
    return settings_dialog.SettingsDialog(wx.Frame(None))


def test_music_tab_controls_exist_and_reflect_config():
    settings_handler.config_set("youtube_music_enabled", True)
    settings_handler.config_set("youtube_music_default_audio_quality", 1)
    dialog = _dialog()
    assert dialog.youtubeMusicEnabled.GetValue() is True
    assert dialog.youtubeMusicQuality.GetSelection() == 1
    assert dialog.youtubeMusicLyrics is not None
    assert dialog.youtubeMusicExplicit is not None
    dialog.Destroy()


def test_music_toggle_disables_dependent_controls():
    settings_handler.config_set("youtube_music_enabled", True)
    dialog = _dialog()
    dialog.youtubeMusicEnabled.SetValue(False)
    dialog._update_youtube_music_controls()
    assert dialog.youtubeMusicLyrics.IsEnabled() is False
    assert dialog.youtubeMusicQuality.IsEnabled() is False
    assert dialog.youtubeMusicImportButton.IsEnabled() is False
    dialog.Destroy()


def test_save_youtube_music_persists_quality():
    dialog = _dialog()
    dialog.youtubeMusicQuality.SetSelection(0)
    dialog._save_youtube_music()
    assert int(settings_handler.config_get("youtube_music_default_audio_quality")) == 0
    dialog.Destroy()


def test_auth_status_reflects_authentication():
    dialog = _dialog()
    with patch("youtube_music.auth_bridge.is_authenticated", return_value=True):
        assert "مسجّل" in dialog._music_auth_status_text()
    with patch("youtube_music.auth_bridge.is_authenticated", return_value=False):
        assert "غير" in dialog._music_auth_status_text()
    dialog.Destroy()


def test_refresh_music_auth_status_reloads_service():
    dialog = _dialog()
    with (
        patch("youtube_music.service.reload_auth") as reload_auth,
        patch("youtube_music.auth_bridge.is_authenticated", return_value=True),
    ):
        dialog._refresh_music_auth_status()
    reload_auth.assert_called_once()
    dialog.Destroy()
