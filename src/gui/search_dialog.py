import logging
import threading

import wx

from language_handler import _
from settings_handler import config_get
from speech_client import speak
from theme_handler import apply_theme
from youtube_browser.search_handler import fetch_search_suggestions

logger = logging.getLogger(__name__)

SEARCH_SUGGESTIONS_DELAY_MS = 750


class SearchDialog(wx.Dialog):
    def __init__(self, parent, value="", show_modal=True):
        wx.Dialog.__init__(self, parent=parent, title=_("بحث"))
        self._closing = False
        self._ignore_text_event = False
        self._request_counter = 0
        self.query = None
        self.filter = None

        self.panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        self.panel.SetMinSize((480, -1))
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Row 1: Search label and text field
        lbl = wx.StaticText(self.panel, -1, _("ابحث في youtube: "))
        self.searchField = wx.TextCtrl(self.panel, -1, value=value)
        self.searchField.SetName(_("ابحث في youtube"))

        sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer1.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer1.Add(self.searchField, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(sizer1, 0, wx.EXPAND)

        # Row 2: Search suggestions ListBox (hidden initially)
        self.suggestionsList = wx.ListBox(
            self.panel,
            -1,
            size=(-1, 150),
            style=wx.LB_SINGLE,
        )
        self.suggestionsList.SetName(_("اقتراحات البحث"))
        self.suggestionsList.Hide()
        main_sizer.Add(self.suggestionsList, 0, wx.EXPAND | wx.ALL, 5)

        # Row 3: Filter label and choice box
        lbl1 = wx.StaticText(self.panel, -1, _("فلتر: "))
        self.filterBox = wx.Choice(
            self.panel,
            -1,
            choices=[
                _("بلا فلتر"),
                _("بث مباشر"),
                _("تاريخ الرفع"),
                _("عدد المشاهدات"),
                _("قائمة تشغيل"),
                _("قنوات"),
            ],
        )
        self.filterBox.Selection = 0
        self.filterBox.SetName(_("فلتر"))

        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer2.Add(lbl1, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer2.Add(self.filterBox, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(sizer2, 0, wx.EXPAND)

        # Row 4: Search and Close buttons
        self.searchButton = wx.Button(self.panel, wx.ID_OK, _("ابحث"))
        self.searchButton.SetDefault()
        self.searchButton.Enable(value.strip() != "")
        self.closeButton = wx.Button(self.panel, wx.ID_CANCEL, _("إغلاق"))

        sizer3 = wx.BoxSizer(wx.HORIZONTAL)
        sizer3.Add(self.searchButton, 1, wx.ALL, 5)
        sizer3.Add(self.closeButton, 1, wx.ALL, 5)
        main_sizer.Add(sizer3, 0, wx.EXPAND)

        self.panel.SetSizer(main_sizer)

        # Debounce timer for suggestions
        self.debounceTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.onDebounceTimer, self.debounceTimer)

        # Event bindings
        self.searchField.Bind(wx.EVT_TEXT, self.onTextChange)
        self.searchField.Bind(wx.EVT_KEY_DOWN, self.onSearchFieldKeyDown)

        self.suggestionsList.Bind(wx.EVT_KEY_DOWN, self.onSuggestionsKeyDown)
        self.suggestionsList.Bind(wx.EVT_SET_FOCUS, self.onSuggestionsSetFocus)
        self.suggestionsList.Bind(wx.EVT_LISTBOX_DCLICK, self.onSuggestionsDClick)
        self.suggestionsList.Bind(wx.EVT_LEFT_UP, self.onSuggestionsLeftUp)

        self.searchButton.Bind(wx.EVT_BUTTON, self.onSearch)
        self.closeButton.Bind(wx.EVT_BUTTON, self.onClose)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

        apply_theme(self)
        self.Fit()
        self.Centre()
        if show_modal:
            self.ShowModal()

    def onTextChange(self, event):
        if self._ignore_text_event or self._closing:
            return

        val = self.searchField.Value.strip()
        self.searchButton.Enable(val != "")

        # Hide previous suggestions while user is actively typing
        if self.suggestionsList.IsShown():
            self._hide_suggestions()

        if self.debounceTimer.IsRunning():
            self.debounceTimer.Stop()

        if not val or not config_get("search_suggestions"):
            return

        self.debounceTimer.StartOnce(SEARCH_SUGGESTIONS_DELAY_MS)

    def onDebounceTimer(self, event):
        if self._closing:
            return
        query = self.searchField.Value.strip()
        if not query or not config_get("search_suggestions"):
            self._hide_suggestions()
            return

        self._request_counter += 1
        req_id = self._request_counter
        threading.Thread(
            target=self._fetch_suggestions_worker,
            args=(query, req_id),
            daemon=True,
        ).start()

    def _fetch_suggestions_worker(self, query, req_id):
        try:
            items = fetch_search_suggestions(query)
        except Exception as e:
            logger.debug(f"Failed to fetch search suggestions for '{query}': {e}")
            items = []

        wx.CallAfter(self._on_suggestions_loaded, query, items, req_id)

    def _on_suggestions_loaded(self, query, items, req_id):
        if self._closing or not self or not bool(self):
            return
        try:
            if not self.searchField or not self.suggestionsList:
                return
        except Exception:
            return

        if req_id != self._request_counter:
            return
        if self.searchField.Value.strip() != query:
            return

        if not items:
            self._hide_suggestions()
            return

        self.suggestionsList.Set(items)
        if not self.suggestionsList.IsShown():
            self.suggestionsList.Show(True)
            self.panel.Layout()
            self.Fit()

        speak(_("تم عرض اقتراحات البحث"), interrupt=False)

    def _hide_suggestions(self):
        if self._closing or not self or not bool(self):
            return
        try:
            if not self.suggestionsList:
                return
            if self.suggestionsList.IsShown():
                self.suggestionsList.Hide()
                self.suggestionsList.Clear()
                self.panel.Layout()
                self.Fit()
        except Exception:
            pass

    def onSearchFieldKeyDown(self, event):
        key = event.GetKeyCode()
        if (
            key == wx.WXK_DOWN
            and self.suggestionsList.IsShown()
            and self.suggestionsList.GetCount() > 0
        ):
            self.suggestionsList.SetFocus()
            self.suggestionsList.SetSelection(0)
            return
        elif key == wx.WXK_RETURN:
            if self.searchButton.IsEnabled():
                self.onSearch(None)
            return
        event.Skip()

    def onSuggestionsKeyDown(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.onSelectSuggestion()
            return
        elif key == wx.WXK_RIGHT:
            self.onRefineSuggestion()
            return
        elif key == wx.WXK_UP and self.suggestionsList.GetSelection() == 0:
            self.searchField.SetFocus()
            return
        elif key == wx.WXK_ESCAPE:
            self._hide_suggestions()
            self.searchField.SetFocus()
            return
        event.Skip()

    def onSuggestionsSetFocus(self, event):
        if (
            self.suggestionsList.GetSelection() == wx.NOT_FOUND
            and self.suggestionsList.GetCount() > 0
        ):
            self.suggestionsList.SetSelection(0)
        event.Skip()

    def onSuggestionsLeftUp(self, event):
        pos = event.GetPosition()
        client_size = self.suggestionsList.GetClientSize()
        if 0 <= pos.x < client_size.width and 0 <= pos.y < client_size.height:
            idx = self.suggestionsList.HitTest(pos)
            if idx != wx.NOT_FOUND and idx < self.suggestionsList.GetCount():
                self.suggestionsList.SetSelection(idx)
                self.onSelectSuggestion()
                return
        event.Skip()

    def onSuggestionsDClick(self, event):
        self.onSelectSuggestion()

    def onSelectSuggestion(self):
        idx = self.suggestionsList.GetSelection()
        if idx != wx.NOT_FOUND:
            suggestion = self.suggestionsList.GetString(idx)
            self._ignore_text_event = True
            self.searchField.SetValue(suggestion)
            self.onSearch(None)

    def onRefineSuggestion(self):
        idx = self.suggestionsList.GetSelection()
        if idx != wx.NOT_FOUND:
            suggestion = self.suggestionsList.GetString(idx)
            self._ignore_text_event = True
            self.searchField.SetValue(suggestion)
            self._ignore_text_event = False
            self.searchButton.Enable(True)
            self._hide_suggestions()
            self.searchField.SetFocus()
            self.searchField.SetInsertionPointEnd()

    def onCharHook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE and self.suggestionsList.IsShown():
            self._hide_suggestions()
            self.searchField.SetFocus()
            return
        event.Skip()

    def onSearch(self, event=None):
        self._closing = True
        if hasattr(self, "debounceTimer") and self.debounceTimer.IsRunning():
            self.debounceTimer.Stop()
        val = self.searchField.Value.strip()
        self.query = val if val != "" else None
        self.filter = self.filterBox.Selection
        self.Destroy()

    def onClose(self, event=None):
        self._closing = True
        if hasattr(self, "debounceTimer") and self.debounceTimer.IsRunning():
            self.debounceTimer.Stop()
        self.query = None
        self.filter = None
        self.Destroy()
