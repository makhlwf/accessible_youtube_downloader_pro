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
    if palette is None and theme_name != "System Default":
        return

    _call_window_method(window, "Freeze")
    try:
        if theme_name == "System Default":
            _apply_system_theme(window, is_root=True)
        else:
            # Convert hex to wx.Colour here, after wx.App is initialized.
            prepared_palette = {
                key: wx.Colour(value) if isinstance(value, str) else value
                for key, value in palette.items()
            }
            _apply_palette(window, prepared_palette)
        _call_theme_hook(window, theme_name)
        _call_window_method(window, "Refresh")
        _call_window_method(window, "Update")
    finally:
        _call_window_method(window, "Thaw")


def apply_theme_to_all_windows(theme_name=None):
    if theme_name is None:
        theme_name = config_get("theme")
    get_top_level_windows = getattr(wx, "GetTopLevelWindows", None)
    if not callable(get_top_level_windows):
        return
    for window in get_top_level_windows():
        apply_theme(window, theme_name)


def _apply_palette(window, palette):
    bg = palette["background"]
    fg = palette["foreground"]

    if _is_wx_instance(window, "CheckBox", "RadioButton", "StaticText", "StaticBox"):
        _set_colours(window, bg, fg)
    elif _is_wx_instance(
        window,
        "TextCtrl",
        "ListBox",
        "Choice",
        "ComboBox",
        "SearchCtrl",
        "SpinCtrl",
        "SpinCtrlDouble",
        "ListCtrl",
        "TreeCtrl",
    ):
        _set_colours(window, palette["text_bg"], palette["text_fg"])
    elif _is_wx_instance(window, "Button", "ToggleButton", "BitmapButton"):
        _set_colours(window, palette["button_bg"], palette["button_fg"])
    else:
        _set_colours(window, bg, fg)

    for child in _get_children(window):
        _apply_palette(child, palette)


def _apply_system_theme(window, is_root=False):
    if is_root:
        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK)
        fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        _set_colours(window, bg, fg)
    else:
        _set_colours(window, wx.NullColour, wx.NullColour)

    for child in _get_children(window):
        _apply_system_theme(child)


def _get_children(window):
    get_children = getattr(window, "GetChildren", None)
    if not callable(get_children):
        return []
    try:
        return list(get_children())
    except RuntimeError, TypeError:
        return []


def _is_wx_instance(window, *class_names):
    for class_name in class_names:
        wx_class = getattr(wx, class_name, None)
        try:
            if wx_class is not None and isinstance(window, wx_class):
                return True
        except TypeError:
            continue
    return False


def _set_colours(window, background, foreground):
    _call_window_method(window, "SetBackgroundColour", background)
    _call_window_method(window, "SetForegroundColour", foreground)


def _call_window_method(window, method_name, *args):
    method = getattr(window, method_name, None)
    if not callable(method):
        return
    try:
        method(*args)
    except AttributeError, RuntimeError:
        return


def _call_theme_hook(window, theme_name):
    hook = getattr(window, "on_theme_applied", None)
    if not callable(hook):
        return
    try:
        hook(theme_name)
    except AttributeError, RuntimeError:
        return
