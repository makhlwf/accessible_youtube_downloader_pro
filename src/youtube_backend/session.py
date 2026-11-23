"""Cookie configuration checks for authenticated YouTube features."""

import os

import wx

from app_state.settings_handler import config_get
from language_handler import _


def ensure_cookies_configured(parent=None, feature_name=None, **kwargs):
    """
    Checks if YouTube cookies file path is configured and exists.
    If missing, alerts user that cookies file is required in Settings.
    Returns True if valid, False otherwise.
    """
    cookies_path = config_get("cookiespath")
    if not cookies_path or not os.path.exists(cookies_path):
        feature = feature_name or kwargs.get("feature_name_ar") or _("هذه الميزة")
        msg_text = _(
            "تنبيه: لم يتم تحديد ملف الكوكيز الخاص بيوتيوب أو أن الملف غير موجود. تتطلب هذه الميزة ({}) ملف كوكيز صالح. يرجى إضافة ملف كوكيز من إعدادات البرنامج."
        ).format(feature)
        title = _("تنبيه")
        dialog_parent = parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None)
        wx.MessageBox(
            msg_text,
            title,
            style=wx.OK | wx.ICON_WARNING,
            parent=dialog_parent,
        )
        return False
    return True


def has_cookies_file():
    cookies_path = config_get("cookiespath")
    return bool(cookies_path and os.path.exists(cookies_path))
