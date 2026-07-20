import wx
from settings_handler import config_get

THEMES = {
    "System Default": None,
    "Light": {
        "background": "#F0F0F0",
        "foreground": "#333333",
        "button_bg": "#E0E0E0",
        "button_fg": "#000000",
        "text_bg": "#FFFFFF",
        "text_fg": "#000000",
    },
    "Dark": {
        "background": "#1A1A1A",
        "foreground": "#E0E0E0",
        "button_bg": "#333333",
        "button_fg": "#FFFFFF",
        "text_bg": "#2D2D2D",
        "text_fg": "#FFFFFF",
    },
    "High Contrast Dark": {
        "background": "#000000",
        "foreground": "#FFFFFF",
        "button_bg": "#000000",
        "button_fg": "#FFFFFF",
        "text_bg": "#000000",
        "text_fg": "#FFFFFF",
    },
}


def apply_theme(window, theme_name=None):
    if theme_name is None:
        theme_name = config_get("theme")
    palette = THEMES.get(theme_name)
    if palette is None:
        if theme_name == "System Default":
            _apply_system_theme(window)
        return

    # Convert hex to wx.Colour here, after wx.App is initialized
    prepared_palette = {
        k: wx.Colour(v) if isinstance(v, str) else v for k, v in palette.items()
    }

    window.Freeze()
    try:
        _apply_palette(window, prepared_palette)
        window.Refresh()
        window.Update()
    finally:
        window.Thaw()


def _apply_palette(window, palette):
    bg = palette["background"]
    fg = palette["foreground"]

    if isinstance(window, (wx.Frame, wx.Panel, wx.Dialog)):
        window.SetBackgroundColour(bg)
        window.SetForegroundColour(fg)

    for child in window.GetChildren():
        if isinstance(child, wx.Button):
            child.SetBackgroundColour(palette["button_bg"])
            child.SetForegroundColour(palette["button_fg"])
        elif isinstance(
            child, (wx.TextCtrl, wx.ListBox, wx.Choice, wx.SpinCtrl, wx.SpinCtrlDouble)
        ):
            child.SetBackgroundColour(palette["text_bg"])
            child.SetForegroundColour(palette["text_fg"])
        elif isinstance(
            child, (wx.StaticText, wx.CheckBox, wx.RadioButton, wx.StaticBox)
        ):
            child.SetForegroundColour(fg)

        # Recurse for panels and sizer-based containers
        if child.GetChildren():
            _apply_palette(child, palette)
        else:
            # Still set colors for leaf nodes if not already handled
            if not isinstance(
                child,
                (
                    wx.Button,
                    wx.TextCtrl,
                    wx.ListBox,
                    wx.Choice,
                    wx.SpinCtrl,
                    wx.SpinCtrlDouble,
                ),
            ):
                child.SetBackgroundColour(bg)
                child.SetForegroundColour(fg)


def _apply_system_theme(window):
    # Reset to system defaults
    bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK)
    fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)

    window.SetBackgroundColour(bg)
    window.SetForegroundColour(fg)

    for child in window.GetChildren():
        child.SetBackgroundColour(wx.NullColour)
        child.SetForegroundColour(wx.NullColour)
        if child.GetChildren():
            _apply_system_theme(child)
