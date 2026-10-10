"""Accessible confirmation dialog for destructive YouTube Music actions.

Destructive operations against the user's real account (delete/rename playlist,
remove from library, unsubscribe, delete a history entry, remove a track) must
be explicitly confirmed. The dialog defaults to "No" and is announced to the
screen reader on open.
"""

import logging

import wx

from language_handler import _
from speech_client import speak

logger = logging.getLogger(__name__)


def confirm_destructive(parent, action_text):
    """Return True only if the user explicitly confirms ``action_text``.

    ``action_text`` is a complete, already-translated question, e.g.
    ``_("حذف قائمة التشغيل '{name}'؟").format(name=...)``.
    """
    speak(action_text)
    dialog = wx.MessageDialog(
        parent,
        action_text,
        _("تأكيد"),
        style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    try:
        return dialog.ShowModal() == wx.ID_YES
    finally:
        dialog.Destroy()
