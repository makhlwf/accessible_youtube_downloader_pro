import os

import wx

_app = wx.App.GetInstance() or wx.App()

import settings_handler
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


def test_search_suggestions_default_setting_exists():
    assert defaults["search_suggestions"] is True


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
    expected_message = "ملف الكوكيز المختار غير موجود."
    expected_caption = "تنبيه"
    assert box_calls[0]["message"] == expected_message
    assert box_calls[0]["caption"] == expected_caption
    assert box_calls[0]["style"] == (wx.OK | wx.ICON_WARNING)
    assert box_calls[0]["parent"] == dialog


def test_browser_cookies_source_setting():
    # Should have a default value of empty string or allow get/set
    source = settings_handler.config_get("browser_cookies_source")
    assert isinstance(source, str)
    settings_handler.config_set("browser_cookies_source", "firefox")
    assert settings_handler.config_get("browser_cookies_source") == "firefox"


def test_browser_cookies_controls_created_and_accessible(monkeypatch):
    import cookies_manager
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.installed_browsers = cookies_manager.get_installed_browsers()
    dialog.browserChoice = wx.Choice(
        wx.Frame(None), -1, choices=[b["name"] for b in dialog.installed_browsers]
    )
    settings_dialog._set_accessible_name(
        dialog.browserChoice, "المتصفح لاستيراد الكوكيز"
    )
    dialog.importBrowserCookiesButton = wx.Button(
        wx.Frame(None), -1, "استيراد من المتصفح"
    )

    assert hasattr(dialog, "browserChoice")
    assert hasattr(dialog, "importBrowserCookiesButton")
    assert isinstance(dialog.browserChoice, wx.Choice)
    assert isinstance(dialog.importBrowserCookiesButton, wx.Button)

    browsers = cookies_manager.get_installed_browsers()
    assert dialog.installed_browsers == browsers

    assert dialog.importBrowserCookiesButton.GetLabel() == "استيراد من المتصفح"
    assert dialog.browserChoice._accessible_label == "المتصفح لاستيراد الكوكيز"


def test_browser_cookies_imported_success(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    dialog.cookiesPathField = wx.TextCtrl(wx.Frame(None), -1)

    box_calls = []

    def fake_messagebox(message, caption, style, parent):
        box_calls.append({"message": message, "caption": caption, "style": style})

    monkeypatch.setattr(wx, "MessageBox", fake_messagebox)

    result = {
        "success": True,
        "count": 12,
        "path": "/mock/browser_cookies.txt",
        "browser": "Mozilla Firefox",
    }
    dialog._on_browser_cookies_imported(result, "firefox")

    assert dialog.cookiesPathField.GetValue() == "/mock/browser_cookies.txt"
    assert dialog.preferences["cookiespath"] == "/mock/browser_cookies.txt"
    assert dialog.preferences["browser_cookies_source"] == "firefox"
    assert len(box_calls) == 1
    assert "12" in box_calls[0]["message"]
    assert "Mozilla Firefox" in box_calls[0]["message"]
    assert box_calls[0]["style"] & wx.ICON_INFORMATION


def test_browser_cookies_imported_locked_error(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    dialog.cookiesPathField = wx.TextCtrl(wx.Frame(None), -1)

    box_calls = []

    def fake_messagebox(message, caption, style, parent):
        box_calls.append({"message": message, "caption": caption, "style": style})

    monkeypatch.setattr(wx, "MessageBox", fake_messagebox)

    result = {
        "success": False,
        "count": 0,
        "error_type": "locked",
        "browser": "Google Chrome",
        "error": "File locked",
    }
    dialog._on_browser_cookies_imported(result, "chrome")

    assert len(box_calls) == 1
    assert "Google Chrome" in box_calls[0]["message"]
    assert box_calls[0]["style"] & wx.ICON_ERROR


def test_browser_cookies_imported_decrypt_failed_error(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    dialog.cookiesPathField = wx.TextCtrl(wx.Frame(None), -1)

    box_calls = []

    def fake_messagebox(message, caption, style, parent):
        box_calls.append({"message": message, "caption": caption, "style": style})

    monkeypatch.setattr(wx, "MessageBox", fake_messagebox)

    result = {
        "success": False,
        "count": 0,
        "error_type": "decrypt_failed",
        "browser": "Google Chrome",
        "error": "DPAPI error",
    }
    dialog._on_browser_cookies_imported(result, "chrome")

    assert len(box_calls) == 1
    assert "Google Chrome" in box_calls[0]["message"]
    assert box_calls[0]["style"] & wx.ICON_ERROR


def test_browser_cookies_imported_no_cookies_error(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    dialog.cookiesPathField = wx.TextCtrl(wx.Frame(None), -1)

    box_calls = []

    def fake_messagebox(message, caption, style, parent):
        box_calls.append({"message": message, "caption": caption, "style": style})

    monkeypatch.setattr(wx, "MessageBox", fake_messagebox)

    result = {
        "success": False,
        "count": 0,
        "error_type": "no_cookies",
        "browser": "Microsoft Edge",
        "error": "No cookies found",
    }
    dialog._on_browser_cookies_imported(result, "edge")

    assert len(box_calls) == 1
    assert "Microsoft Edge" in box_calls[0]["message"]
    assert box_calls[0]["style"] & wx.ICON_ERROR


def test_on_import_browser_cookies_disables_button_and_shifts_focus(monkeypatch):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.installed_browsers = [{"id": "firefox", "name": "Firefox"}]

    frame = wx.Frame(None)
    dialog.browserChoice = wx.Choice(frame, -1, choices=["Firefox"])
    dialog.browserChoice.Selection = 0
    dialog.importBrowserCookiesButton = wx.Button(frame, -1)

    thread_started = []

    class FakeThread:
        def __init__(self, target, daemon=None):
            self.target = target
            thread_started.append(self)

        def start(self):
            pass

    monkeypatch.setattr(settings_dialog.threading, "Thread", FakeThread)

    monkeypatch.setattr(dialog.importBrowserCookiesButton, "HasFocus", lambda: True)
    focused_control = []
    monkeypatch.setattr(
        dialog.browserChoice,
        "SetFocus",
        lambda: focused_control.append("browserChoice"),
    )

    dialog.onImportBrowserCookies()

    assert dialog.importBrowserCookiesButton.IsEnabled() is False
    assert focused_control == ["browserChoice"]
    assert len(thread_started) == 1

    dialog.onImportBrowserCookies()
    assert len(thread_started) == 1


def test_browser_cookies_imported_reenables_button_on_success_and_failure(
    monkeypatch,
):
    from gui import settings_dialog

    dialog = settings_dialog.SettingsDialog.__new__(settings_dialog.SettingsDialog)
    dialog.preferences = {}
    frame = wx.Frame(None)
    dialog.cookiesPathField = wx.TextCtrl(frame, -1)
    dialog.importBrowserCookiesButton = wx.Button(frame, -1)
    dialog.importBrowserCookiesButton.Disable()
    assert dialog.importBrowserCookiesButton.IsEnabled() is False

    monkeypatch.setattr(wx, "MessageBox", lambda *args, **kwargs: None)

    dialog._on_browser_cookies_imported(
        {
            "success": True,
            "count": 5,
            "path": "/path/to/cookies.txt",
            "browser": "Firefox",
        },
        "firefox",
    )
    assert dialog.importBrowserCookiesButton.IsEnabled() is True

    dialog.importBrowserCookiesButton.Disable()
    assert dialog.importBrowserCookiesButton.IsEnabled() is False

    dialog._on_browser_cookies_imported(
        {"success": False, "error_type": "locked", "browser": "Chrome"}, "chrome"
    )
    assert dialog.importBrowserCookiesButton.IsEnabled() is True


def _skip_test():
    import settings_handler
    from gui import settings_dialog

    settings_handler.config_initialization()

    settings_handler.config_set("defaultformat", "0")
    dialog = settings_dialog.SettingsDialog(wx.Frame(None))

    assert dialog.formats.GetCount() == 6
    assert dialog.formats.GetString(0) == "فيديو (mp4)"
    assert dialog.formats.GetString(1) == "فيديو (mkv)"
    assert dialog.formats.GetString(2) == "صوت (m4a)"
    assert dialog.formats.GetString(3) == "صوت (mp3)"
    assert dialog.formats.GetString(4) == "صوت (wav)"
    assert dialog.formats.GetString(5) == "صوت (flac)"

    assert dialog.formats.Selection == 0
    dialog.Destroy()

    settings_handler.config_set("defaultformat", "9")
    dialog = settings_dialog.SettingsDialog(wx.Frame(None))
    assert dialog.formats.Selection == 0
    dialog.Destroy()


def test_settings_dialog_defaultformat_choices_fixed():
    import settings_handler
    from gui import settings_dialog

    settings_handler.config_initialization()

    settings_handler.config_set("defaultformat", "0")
    dialog = settings_dialog.SettingsDialog(wx.Frame(None))

    assert dialog.formats.GetCount() == 6
    strings = dialog.formats.GetStrings()
    assert strings[0] == "فيديو (mp4)"
    assert strings[1] == "فيديو (mkv)"
    assert strings[2] == "صوت (m4a)"
    assert strings[3] == "صوت (mp3)"
    assert strings[4] == "صوت (wav)"
    assert strings[5] == "صوت (flac)"

    assert dialog.formats.Selection == 0
    dialog.Destroy()

    settings_handler.config_set("defaultformat", "9")
    dialog = settings_dialog.SettingsDialog(wx.Frame(None))
    assert dialog.formats.Selection == 0
    dialog.Destroy()
