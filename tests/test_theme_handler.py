import os
import sys
from unittest.mock import patch

# Add application source directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# We need to import wx AFTER the mock is set up by conftest
import wx


def test_theme_handler_import():
    import theme_handler

    assert theme_handler is not None


def test_apply_theme_dark():
    from theme_handler import apply_theme

    frame = wx.Frame()
    panel = wx.Panel()
    button = wx.Button()
    text = wx.StaticText()

    frame.GetChildren.return_value = [panel]
    panel.GetChildren.return_value = [button, text]

    apply_theme(frame, "Dark")

    # Verify root background/foreground reset to system colors
    frame.SetBackgroundColour.assert_called()
    frame.SetForegroundColour.assert_called()


def test_apply_theme_system_default():
    from theme_handler import apply_theme

    frame = wx.Frame()

    with patch("theme_handler.config_get", return_value="System Default"):
        apply_theme(frame)

    # Verify SystemSettings was called
    wx.SystemSettings.GetColour.assert_called()
    frame.SetBackgroundColour.assert_called()
    frame.SetForegroundColour.assert_called()


def test_apply_theme_config_get():
    from theme_handler import apply_theme

    frame = wx.Frame()

    with patch("theme_handler.config_get", return_value="Light"):
        apply_theme(frame)

    frame.SetBackgroundColour.assert_called()


def test_update_msw_dark_mode():
    from unittest.mock import MagicMock

    from theme_handler import update_msw_dark_mode

    mock_app = MagicMock()
    mock_app.MSWEnableDarkMode = MagicMock()

    with (
        patch.object(wx, "GetApp", return_value=mock_app),
        patch.object(wx, "App", getattr(wx, "App", MagicMock())),
    ):
        wx.App.DarkMode_Auto = 0
        wx.App.DarkMode_Always = 1

        update_msw_dark_mode("Dark")
        mock_app.MSWEnableDarkMode.assert_called_with(1)

        update_msw_dark_mode("System Default")
        mock_app.MSWEnableDarkMode.assert_called_with(0)

        update_msw_dark_mode("Light")
        mock_app.MSWEnableDarkMode.assert_called_with(0)
