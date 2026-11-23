import inspect
import logging
from threading import Thread

import wx

from app_runtime.async_utils import run_in_async_loop
from gui.theme_handler import apply_theme

logger = logging.getLogger(__name__)


class LoadingDialog(wx.Dialog):
    def __init__(self, parent, msg, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.res = None
        self.error = None
        self.cancelled = False
        self._finished = False
        super().__init__(parent)
        self.CenterOnParent()
        p = wx.Panel(self)
        self.message = wx.StaticText(p, -1, msg)
        self.message.SetCanFocus(True)
        self.message.SetFocus()
        indicator = wx.ActivityIndicator(p)
        indicator.Start()
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.message, 1, wx.EXPAND)
        sizer.AddStretchSpacer()
        sizer.Add(indicator, 1, wx.EXPAND)
        sizer.AddStretchSpacer()
        p.SetSizer(sizer)
        apply_theme(self)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        Thread(target=self.run, daemon=True).start()
        try:
            self.ShowModal()
        finally:
            self._finished = True
            self.Destroy()

    def run(self):
        try:
            result = self.function(*self.args, **self.kwargs)
            if inspect.isawaitable(result):
                result = run_in_async_loop(result)
        except Exception as error:
            logger.exception("Loading dialog task failed")
            wx.CallAfter(self._finish, None, error)
        else:
            wx.CallAfter(self._finish, result, None)

    def _finish(self, result, error):
        if self._finished:
            return
        self._finished = True
        self.res = result
        self.error = error
        self.EndModal(wx.ID_OK if error is None else wx.ID_CANCEL)

    def onHook(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.onClose(event)
            return
        if event.KeyCode in (wx.WXK_DOWN, wx.WXK_UP, wx.WXK_LEFT, wx.WXK_RIGHT):
            self.message.SetFocus()
            return
        event.Skip()

    def onClose(self, event):
        self.cancelled = True
        self._finished = True
        self.EndModal(wx.ID_CANCEL)
