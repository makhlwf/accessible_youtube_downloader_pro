import inspect
from unittest.mock import MagicMock, patch

import utils
from youtube_backend.pot_provider_service import pot_service


def test_get_pot_provider_version():
    with patch.object(pot_service, "get_installed_version", return_value="v0.8.1"):
        assert utils.get_pot_provider_version() == "v0.8.1"


def test_update_pot_provider_already_latest():
    with (
        patch.object(pot_service, "get_installed_version", return_value="v0.8.1"),
        patch("app_runtime.dependencies.get_latest_github_release", return_value="v0.8.1"),
        patch("wx.MessageBox") as mock_box,
    ):
        utils.update_pot_provider()
        mock_box.assert_called_once()


def test_update_pot_provider_updates_when_available():
    with (
        patch.object(pot_service, "get_installed_version", return_value="v0.8.0"),
        patch("app_runtime.dependencies.get_latest_github_release", return_value="v0.8.1"),
        patch("wx.MessageBox", return_value=5100),
        patch("wx.YES", 5100),
        patch.object(
            pot_service, "download_and_install", return_value=True
        ) as mock_install,
    ):
        res = utils.update_pot_provider()
        assert res is True
        mock_install.assert_called_once()


def test_update_pot_provider_no_release():
    with (
        patch.object(pot_service, "get_installed_version", return_value="v0.8.0"),
        patch("app_runtime.dependencies.get_latest_github_release", return_value=None),
        patch("app_runtime.dependencies.show_error") as mock_err,
    ):
        res = utils.update_pot_provider()
        assert res is False
        mock_err.assert_called_once()


def test_settings_dialog_has_pot_provider_checkbox():
    from gui.settings_dialog import SettingsDialog

    # Verify SettingsDialog has references to pot_provider_enabled
    source = inspect.getsource(SettingsDialog._build_advanced_page)
    assert "pot_provider_enabled" in source


def test_main_screen_has_pot_provider_menu_and_startup():
    from gui import home_screen

    source = inspect.getsource(home_screen.HomeScreen)
    assert "showPotProviderVer" in source
    assert "updatePotProvider" in source
    assert "on_show_pot_provider_version" in source
    assert "on_update_pot_provider" in source
    startup_source = inspect.getsource(home_screen.HomeScreen.startup_dependency_checks)
    assert "check_pot_provider" in startup_source


def test_home_screen_on_show_pot_provider_version():
    from gui import home_screen

    fake_self = MagicMock()

    # Not installed
    with (
        patch("utils.get_pot_provider_version", return_value=None),
        patch("wx.MessageBox") as mock_box,
    ):
        home_screen.HomeScreen.on_show_pot_provider_version(fake_self, None)
        mock_box.assert_called_once()
        assert "غير مثبتة" in mock_box.call_args[0][0]

    # Installed & healthy
    with (
        patch("utils.get_pot_provider_version", return_value="v0.8.1"),
        patch.object(pot_service, "is_healthy", return_value=True),
        patch("wx.MessageBox") as mock_box,
    ):
        home_screen.HomeScreen.on_show_pot_provider_version(fake_self, None)
        mock_box.assert_called_once()
        msg = mock_box.call_args[0][0]
        assert "v0.8.1" in msg
        assert "قيد التشغيل" in msg


def test_home_screen_on_update_pot_provider():
    from gui import home_screen

    fake_self = MagicMock()
    with patch("utils.update_pot_provider") as mock_update:
        home_screen.HomeScreen.on_update_pot_provider(fake_self, None)
        mock_update.assert_called_once_with(parent=fake_self)


def test_home_screen_startup_dependency_checks():
    from gui import home_screen

    fake_self = MagicMock()
    fake_self._shutting_down.is_set.return_value = False
    with (
        patch("utils.check_yt_dlp", return_value=True),
        patch("utils.check_deno", return_value=True),
        patch("utils.ensure_js_dependencies") as mock_ensure,
        patch.object(home_screen.pot_service, "is_installed", return_value=False),
        patch("utils.check_pot_provider") as mock_check_pot,
    ):
        home_screen.HomeScreen.startup_dependency_checks(fake_self)
        mock_ensure.assert_called_once()
        mock_check_pot.assert_called_once_with(fake_self)


def test_home_screen_starts_installed_provider_off_gui_thread():
    from gui import home_screen

    home = MagicMock()
    home._shutting_down.is_set.return_value = False
    with (
        patch("utils.check_yt_dlp", return_value=False),
        patch("utils.check_pot_provider") as gui_check,
        patch.object(home_screen.pot_service, "is_installed", return_value=True),
        patch.object(home_screen.threading, "Thread") as worker,
    ):
        home_screen.HomeScreen.startup_dependency_checks(home)

    gui_check.assert_not_called()
    worker.assert_called_once_with(
        target=home._start_installed_pot_provider, daemon=True
    )
    worker.return_value.start.assert_called_once()
