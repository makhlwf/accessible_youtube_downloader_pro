import wx
from threading import Thread
import inspect
import logging
from async_utils import run_in_async_loop
from theme_handler import apply_theme

logger = logging.getLogger(__name__)


class LoadingDialog(wx.Dialog):
    def __init__(self, parent, msg, function, *args, **kwargs):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.res = None
        self.error = None
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
        self.ShowModal()

    def run(self):
        try:
            if inspect.iscoroutinefunction(self.function):
                # Run async function in the asyncio loop
                self.res = run_in_async_loop(self.function(*self.args, **self.kwargs))
            else:
                # Run synchronous function in the current thread
                self.res = self.function(*self.args, **self.kwargs)
            wx.CallAfter(self.Destroy)
        except Exception as e:
            self.error = e
            logger.exception("Loading dialog task failed")
            wx.CallAfter(self.Destroy)

    def onHook(self, event):
        if event.KeyCode in (wx.WXK_DOWN, wx.WXK_UP, wx.WXK_LEFT, wx.WXK_RIGHT):
            self.message.SetFocus()
            return
        event.Skip()

    def onClose(self, event):
        self.Destroy()
