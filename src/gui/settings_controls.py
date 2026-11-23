"""Accessible names and checkbox state for settings controls."""

import wx


def _accessible_name(label):
    return str(label).replace("&", "").strip().rstrip(":：").strip()


_WX_ACCESSIBLE_BASE = getattr(wx, "Accessible", None)
if not isinstance(_WX_ACCESSIBLE_BASE, type):
    _WX_ACCESSIBLE_BASE = object


def _wx_constant(name, fallback):
    value = getattr(wx, name, fallback)
    return value if isinstance(value, int) else fallback


class ControlAccessible(_WX_ACCESSIBLE_BASE):
    def __init__(self, control):
        if _WX_ACCESSIBLE_BASE is object:
            super().__init__()
        else:
            super().__init__(control)
        self.control = control

    def GetName(self, child_id):
        label = getattr(self.control, "_accessible_label", "")
        if not label:
            get_name = getattr(self.control, "GetName", None)
            if callable(get_name):
                label = get_name()
            elif hasattr(self.control, "Name"):
                label = getattr(self.control, "Name", "")
        return _wx_constant("ACC_OK", 0), _accessible_name(label or "")


def set_control_accessible_name(control, label):
    name = _accessible_name(label)
    if name:
        set_name = getattr(control, "SetName", None)
        if callable(set_name):
            set_name(name)
        control._accessible_label = name
        set_accessible = getattr(control, "SetAccessible", None)
        if callable(set_accessible) and _WX_ACCESSIBLE_BASE is not object:
            try:
                if not getattr(control, "_accessible", None):
                    control._accessible = ControlAccessible(control)
                    set_accessible(control._accessible)
            except Exception:
                control._accessible = None


class CheckBoxAccessible(_WX_ACCESSIBLE_BASE):
    def __init__(self, control):
        if _WX_ACCESSIBLE_BASE is object:
            super().__init__()
        else:
            super().__init__(control)
        self.control = control

    def GetName(self, child_id):
        label = getattr(self.control, "_accessible_label", "")
        get_label = getattr(self.control, "GetLabel", None)
        if not label and callable(get_label):
            label = get_label()
        return _wx_constant("ACC_OK", 0), _accessible_name(label)

    def GetRole(self, child_id):
        return _wx_constant("ACC_OK", 0), _wx_constant("ROLE_SYSTEM_CHECKBUTTON", 0x2C)

    def GetState(self, child_id):
        state = _wx_constant("ACC_STATE_SYSTEM_FOCUSABLE", 0x100000)
        get_value = getattr(self.control, "GetValue", None)
        if callable(get_value) and get_value():
            state |= _wx_constant("ACC_STATE_SYSTEM_CHECKED", 0x10)
        is_enabled = getattr(self.control, "IsEnabled", None)
        if callable(is_enabled) and not is_enabled():
            state |= _wx_constant("ACC_STATE_SYSTEM_UNAVAILABLE", 0x1)
        has_focus = getattr(self.control, "HasFocus", None)
        if callable(has_focus) and has_focus():
            state |= _wx_constant("ACC_STATE_SYSTEM_FOCUSED", 0x4)
        return _wx_constant("ACC_OK", 0), state


class SettingsCheckBox(wx.CheckBox):
    def __init__(self, parent, id, label, **kwargs):
        super().__init__(parent, id, label, **kwargs)
        self._accessible_label = _accessible_name(label)
        self._accessible = None
        set_accessible = getattr(self, "SetAccessible", None)
        if callable(set_accessible) and _WX_ACCESSIBLE_BASE is not object:
            try:
                self._accessible = CheckBoxAccessible(self)
                set_accessible(self._accessible)
            except Exception:
                self._accessible = None
