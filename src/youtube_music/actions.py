"""Run YouTube Music write operations off the GUI thread, with confirmation.

All ytmusicapi writes hit the network and must run on a daemon thread; results
are marshalled back with ``wx.CallAfter``. Destructive writes are gated by
:func:`confirm_destructive` first. Success and failure are announced to the
screen reader, and an :class:`AuthRequiredError` routes to the sign-in prompt
rather than a generic error.
"""

import logging
from threading import Thread

import wx

from language_handler import _
from speech_client import speak

from .dialogs import confirm_destructive
from .errors import AuthRequiredError

logger = logging.getLogger(__name__)


def run_write(
    frame,
    panel,
    fn,
    *,
    success_msg,
    destructive=False,
    confirm_text="",
    refresh=True,
):
    """Execute ``fn`` (a zero-arg service call) on a worker thread.

    ``frame`` hosts the confirmation dialog; ``panel`` is refreshed on success
    when ``refresh`` is True. Returns immediately; the outcome is spoken.
    """
    if destructive and not confirm_destructive(frame, confirm_text):
        speak(_("تم الإلغاء"))
        return

    def worker():
        try:
            fn()
            error = None
        except Exception as exc:
            error = exc
        wx.CallAfter(_done, error)

    def _done(error):
        if error is None:
            speak(success_msg)
            if refresh and panel is not None:
                panel.reload_current()
            return
        if isinstance(error, AuthRequiredError):
            if panel is not None:
                panel.prompt_sign_in()
            else:
                speak(_("يلزم تسجيل الدخول"))
            return
        logger.warning("YouTube Music write failed", exc_info=error)
        speak(_("فشلت العملية"))

    Thread(target=worker, daemon=True).start()
