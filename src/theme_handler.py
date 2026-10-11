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
}


def update_msw_dark_mode(theme_name=None):
    """Enable or disable OS-level dark mode on Windows (MSWEnableDarkMode) for title bars, menus, dialogs, and controls (wxPython 4.3.0+)."""
    if theme_name is None:
        theme_name = config_get("theme")

    get_app = getattr(wx, "GetApp", None)
    if not callable(get_app):
        get_app = getattr(getattr(wx, "App", None), "Get", None)

    if not callable(get_app):
        return

    try:
        app = get_app()
    except Exception:
        app = None

    if not app:
        return

    msw_enable_dark_mode = getattr(app, "MSWEnableDarkMode", None)
    if not callable(msw_enable_dark_mode):
        return

    wx_app_class = getattr(wx, "App", None)

    try:
        if theme_name == "Dark":
            always_flag = getattr(wx_app_class, "DarkMode_Always", 1)
            msw_enable_dark_mode(always_flag)
        elif theme_name == "Light":
            msw_enable_dark_mode(0)
        else:
            # System Default
            auto_flag = getattr(wx_app_class, "DarkMode_Auto", 0)
            msw_enable_dark_mode(auto_flag)
    except Exception:
        pass


def apply_theme(window, theme_name=None):
    if theme_name is None:
        theme_name = config_get("theme")

    update_msw_dark_mode(theme_name)

    palette = THEMES.get(theme_name)

    _call_window_method(window, "Freeze")
    try:
        if theme_name == "System Default" or palette is None:
            _apply_system_theme(window, is_root=True)
        else:
            prepared_palette = {
                key: wx.Colour(value) if isinstance(value, str) else value
                for key, value in palette.items()
            }
            _apply_palette(window, prepared_palette, theme_name=theme_name)
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


def _on_dark_button_paint(event):
    button = event.GetEventObject()
    dc = wx.PaintDC(button)
    rect = button.GetClientRect()

    bg = button.GetBackgroundColour()
    fg = button.GetForegroundColour()

    if not bg.IsOk() or bg == wx.NullColour:
        bg = wx.Colour("#333333")
    if not fg.IsOk() or fg == wx.NullColour:
        fg = wx.Colour("#FFFFFF")

    # Fill background
    dc.SetBackground(wx.Brush(bg))
    dc.Clear()

    # Draw rounded border (highlight when focused)
    border_color = wx.Colour("#007ACC") if button.HasFocus() else wx.Colour("#555555")
    dc.SetPen(wx.Pen(border_color, 1))
    dc.SetBrush(wx.Brush(bg))
    dc.DrawRoundedRectangle(rect, 4)

    # Draw button text label centered
    label = button.GetLabel()
    if label:
        dc.SetTextForeground(fg)
        dc.SetFont(button.GetFont())
        tw, th = dc.GetTextExtent(label)
        dc.DrawText(
            label, max(0, (rect.width - tw) // 2), max(0, (rect.height - th) // 2)
        )


def _apply_dark_button_style(window, bg, fg):
    _set_colours(window, bg, fg)
    if getattr(wx, "Platform", "") == "__WXMSW__":
        if not getattr(window, "_dark_paint_bound", False):
            window.Bind(wx.EVT_PAINT, _on_dark_button_paint)
            window.Bind(wx.EVT_SET_FOCUS, lambda e: (window.Refresh(), e.Skip()))
            window.Bind(wx.EVT_KILL_FOCUS, lambda e: (window.Refresh(), e.Skip()))
            window._dark_paint_bound = True
        _call_window_method(window, "Refresh")


def _remove_dark_button_style(window):
    if getattr(window, "_dark_paint_bound", False):
        try:
            window.Unbind(wx.EVT_PAINT)
        except Exception:
            pass
        window._dark_paint_bound = False
        _call_window_method(window, "Refresh")


def _apply_palette(window, palette, theme_name=None):
    is_dark_theme = theme_name == "Dark"

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
        if is_dark_theme:
            _apply_dark_button_style(window, palette["button_bg"], palette["button_fg"])
        else:
            _remove_dark_button_style(window)
            _set_colours(window, palette["button_bg"], palette["button_fg"])
    else:
        _set_colours(window, bg, fg)

    for child in _get_children(window):
        _apply_palette(child, palette, theme_name=theme_name)


def _apply_system_theme(window, is_root=False):
    if _is_wx_instance(window, "Button", "ToggleButton", "BitmapButton"):
        _remove_dark_button_style(window)

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
