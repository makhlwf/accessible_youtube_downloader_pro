from unittest.mock import patch
import os
import sys

# Add source directory to path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source"))
)

# We need to import wx AFTER the mock is set up by conftest
import wx


def test_theme_handler_import():
    import theme_handler

    assert theme_handler is not None


def test_apply_theme_dark():
    from theme_handler import apply_theme, THEMES

    frame = wx.Frame()
    panel = wx.Panel()
    button = wx.Button()
    text = wx.StaticText()

    frame.GetChildren.return_value = [panel]
    panel.GetChildren.return_value = [button, text]

    apply_theme(frame, "Dark")

    dark_palette = THEMES["Dark"]

    # Verify colors were set
    frame.SetBackgroundColour.assert_called_with(dark_palette["background"])
    frame.SetForegroundColour.assert_called_with(dark_palette["foreground"])
    panel.SetBackgroundColour.assert_called_with(dark_palette["background"])
    panel.SetForegroundColour.assert_called_with(dark_palette["foreground"])
    button.SetBackgroundColour.assert_called_with(dark_palette["button_bg"])
    button.SetForegroundColour.assert_called_with(dark_palette["button_fg"])
    text.SetForegroundColour.assert_called_with(dark_palette["foreground"])


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
    from theme_handler import apply_theme, THEMES

    frame = wx.Frame()

    with patch("theme_handler.config_get", return_value="Light"):
        apply_theme(frame)

    light_palette = THEMES["Light"]
    frame.SetBackgroundColour.assert_called_with(light_palette["background"])
