import os

import wx

_app = wx.App.GetInstance() or wx.App()

from paths import settings_path
from settings_handler import config_get, config_initialization, config_set, defaults


def _reset_settings_module(settings_handler):
    if settings_handler._save_timer:
        settings_handler._save_timer.cancel()
        settings_handler._save_timer = None
    settings_handler._cache = {}
    settings_handler._config = settings_handler._new_config()


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
    assert config_get("audiooutputdevice") == defaults["audiooutputdevice"]

    # Test setting values
    config_set("eq_enabled", True)
    assert config_get("eq_enabled") is True

    # Cleanup
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))


def test_theme_default():
    # Ensure fresh settings
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))
    config_initialization()

    # Verify default theme
    assert config_get("theme") == "System Default"

    # Cleanup
    if os.path.exists(os.path.join(settings_path, "settings.ini")):
        os.remove(os.path.join(settings_path, "settings.ini"))


def test_player_fullscreen_default_setting_exists():
    assert defaults["player_fullscreen_default"] is False


def test_settings_checkbox_accessible_role_uses_checkbutton():
    from gui import settings_dialog

    class FakeControl:
        _accessible_label = "Open fullscreen"

        def GetValue(self):
            return True

        def IsEnabled(self):
            return True

        def HasFocus(self):
            return False

    accessible = settings_dialog.CheckBoxAccessible(FakeControl())

    assert accessible.GetName(0) == (0, "Open fullscreen")
    assert accessible.GetRole(0) == (0, 0x2C)
    assert accessible.GetState(0)[1] & 0x10


def test_control_accessible_name():
    from gui import settings_dialog

    class FakeControl:
        _accessible_label = "مسار مجلد التنزيل"
        Name = "path"

    accessible = settings_dialog.ControlAccessible(FakeControl())
    assert accessible.GetName(0) == (0, "مسار مجلد التنزيل")


def test_set_accessible_name_attaches_accessible():
    from gui import settings_dialog

    class FakeControl:
        def SetName(self, name):
            self.Name = name

        def SetAccessible(self, accessible):
            self._accessible = accessible

    ctrl = FakeControl()
    settings_dialog._set_accessible_name(ctrl, "مسار ملف الكوكيز: ")

    assert ctrl._accessible_label == "مسار ملف الكوكيز"
    if settings_dialog._WX_ACCESSIBLE_BASE is not object:
        assert isinstance(ctrl._accessible, settings_dialog.ControlAccessible)
        assert ctrl._accessible.GetName(0) == (0, "مسار ملف الكوكيز")


def test_settings_repeat_checkbox_disables_autoplay(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}

    class FakeCheckbox:
        def __init__(self, name, value):
            self.Name = name
            self.Value = value

        def GetValue(self):
            return self.Value

        def SetValue(self, value):
            self.Value = value

    class FakeEvent:
        def __init__(self, obj):
            self.EventObject = obj

    dialog.repeateTracks = FakeCheckbox("repeatTracks", True)
    dialog.autoPlayNext = FakeCheckbox("autonext", True)

    config = {"repeatTracks": False, "autonext": True}
    monkeypatch.setattr(settings_dialog, "config_get", lambda key: config[key])

    dialog.onCheck(FakeEvent(dialog.repeateTracks))

    assert dialog.autoPlayNext.Value is False
    assert dialog.preferences == {"autonext": False, "repeatTracks": True}


def test_settings_load_legacy_lowercase_keys(monkeypatch, tmp_path):
    import settings_handler

    current_path = tmp_path / "HexPlayer"
    legacy_path = tmp_path / "accessible youtube downloader pro"
    legacy_path.mkdir()
    (legacy_path / "settings.ini").write_text(
        "[settings]\nrepeattracks = true\npath = C:\\legacy\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_handler, "settings_path", str(current_path))
    monkeypatch.setattr(settings_handler, "legacy_settings_paths", [str(legacy_path)])
    _reset_settings_module(settings_handler)

    settings_handler.config_initialization()

    assert settings_handler.config_get("repeatTracks") is True
    assert settings_handler.config_get("repeattracks") is True
    assert settings_handler.config_get("path") == "C:\\legacy"
    saved = (current_path / "settings.ini").read_text(encoding="utf-8")
    assert "repeatTracks = True" in saved


def test_settings_merge_newest_file_with_missing_keys(monkeypatch, tmp_path):
    import settings_handler

    current_path = tmp_path / "HexPlayer"
    legacy_path = tmp_path / "accessible youtube downloader pro"
    current_path.mkdir()
    legacy_path.mkdir()
    current_file = current_path / "settings.ini"
    legacy_file = legacy_path / "settings.ini"
    current_file.write_text(
        "[settings]\npath = C:\\current\nplayer_fullscreen_default = True\n",
        encoding="utf-8",
    )
    legacy_file.write_text("[settings]\npath = C:\\legacy\n", encoding="utf-8")
    os.utime(current_file, (1000, 1000))
    os.utime(legacy_file, (2000, 2000))
    monkeypatch.setattr(settings_handler, "settings_path", str(current_path))
    monkeypatch.setattr(settings_handler, "legacy_settings_paths", [str(legacy_path)])
    _reset_settings_module(settings_handler)

    settings_handler.config_initialization()

    assert settings_handler.config_get("path") == "C:\\legacy"
    assert settings_handler.config_get("player_fullscreen_default") is True


def test_validate_cookies_path_empty_returns_true():
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    assert dialog.validate_cookies_path("") is True
    assert dialog.validate_cookies_path(None) is True


def test_validate_cookies_path_existing_file_returns_true(tmp_path):
    from gui import settings_dialog

    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text("test", encoding="utf-8")
    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    assert dialog.validate_cookies_path(str(cookies_file)) is True


def test_validate_cookies_path_nonexistent_returns_false_and_shows_messagebox(
    monkeypatch, tmp_path
):
    import utils
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    non_existent = tmp_path / "does_not_exist.txt"

    box_calls = []

    def fake_messagebox(message, caption, style, parent):
        box_calls.append(
            {
                "message": message,
                "caption": caption,
                "style": style,
                "parent": parent,
            }
        )

    monkeypatch.setattr(wx, "MessageBox", fake_messagebox)

    result = dialog.validate_cookies_path(str(non_existent))

    assert result is False
    assert len(box_calls) == 1
    expected_message = utils.format_bilingual_message(
        "ملف الكوكيز المختار غير موجود.",
        "Selected cookies file does not exist.",
    )
    expected_caption = utils.format_bilingual_message("تنبيه", "Notice")
    assert box_calls[0]["message"] == expected_message
    assert box_calls[0]["caption"] == expected_caption
    assert box_calls[0]["style"] == (wx.OK | wx.ICON_WARNING)
    assert box_calls[0]["parent"] == dialog
