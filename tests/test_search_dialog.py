import unittest
from unittest.mock import MagicMock, patch

import wx

from gui.search_dialog import SearchDialog
from language_handler import _


class MockKeyEvent:
    """Mock key event for testing keyboard navigation hooks."""

    def __init__(self, key_code):
        self._key_code = key_code
        self.skipped = False

    def GetKeyCode(self):
        return self._key_code

    def Skip(self, val=True):
        self.skipped = bool(val)


class MockMouseEvent:
    """Mock mouse event for testing click selection."""

    def __init__(self, pos):
        self._pos = pos
        self.skipped = False

    def GetPosition(self):
        return self._pos

    def Skip(self, val=True):
        self.skipped = bool(val)


class TestSearchDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App()

    def setUp(self):
        self.history_patch = patch("gui.search_dialog.SearchHistory")
        self.history = self.history_patch.start()
        self.addCleanup(self.history_patch.stop)
        self.history.get_recent.return_value = []
        self.history.add.return_value = True
        self.history.clear.return_value = True
        self.dialog = SearchDialog(None, value="", show_modal=False)

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.Destroy()
            except Exception:
                pass
        wx.Yield()

    def test_history_loaded_and_named(self):
        self.dialog.Destroy()
        self.history.get_recent.return_value = ["latest", "older"]
        self.dialog = SearchDialog(None, show_modal=False)
        assert self.dialog.historyList.GetName() == _("Recent searches")
        assert self.dialog.historyList.GetString(0) == "latest"
        assert self.dialog.clearHistoryButton.IsEnabled()
        self.dialog.onSearchFieldKeyDown(MockKeyEvent(wx.WXK_DOWN))
        assert self.dialog.historyList.GetSelection() == 0
        assert self.dialog.FindFocus() == self.dialog.historyList

    def test_history_empty_disables_controls(self):
        assert not self.dialog.historyList.IsEnabled()
        assert not self.dialog.clearHistoryButton.IsEnabled()

    def test_history_enter_submits_and_saves(self):
        self.dialog.historyList.Set(["saved search"])
        self.dialog.historyList.SetSelection(0)
        self.dialog.onHistoryKeyDown(MockKeyEvent(wx.WXK_RETURN))
        assert self.dialog.query == "saved search"
        self.history.add.assert_called_once_with("saved search")

    def test_history_refine_stops_stale_suggestions(self):
        self.dialog.historyList.Set(["saved search"])
        self.dialog.historyList.SetSelection(0)
        self.dialog._request_counter = 1
        self.dialog.debounceTimer.StartOnce(750)
        self.dialog.onHistoryKeyDown(MockKeyEvent(wx.WXK_SPACE))
        assert self.dialog.searchField.Value == "saved search"
        assert self.dialog.FindFocus() == self.dialog.searchField
        assert not self.dialog.debounceTimer.IsRunning()
        assert not self.dialog._closing
        self.dialog._on_suggestions_loaded("saved search", ["stale"], 1)
        assert not self.dialog.suggestionsList.IsShown()
        self.history.add.assert_not_called()

    @patch("gui.search_dialog.speak")
    @patch("gui.search_dialog.wx.MessageBox", return_value=wx.YES)
    def test_clear_history(self, message_box, speak):
        self.dialog.historyList.Set(["saved"])
        self.dialog.onClearHistory()
        self.history.clear.assert_called_once()
        assert self.dialog.historyList.GetCount() == 0
        assert not self.dialog.clearHistoryButton.IsEnabled()
        assert self.dialog.FindFocus() == self.dialog.searchField
        speak.assert_called_once_with(_("Search history cleared"), interrupt=True)

    @patch("gui.search_dialog.wx.MessageBox", return_value=wx.NO)
    def test_clear_history_cancelled(self, message_box):
        self.dialog.historyList.Set(["saved"])
        self.dialog.onClearHistory()
        self.history.clear.assert_not_called()
        assert self.dialog.historyList.GetCount() == 1

    @patch("gui.search_dialog.speak")
    @patch("gui.search_dialog.wx.MessageBox", return_value=wx.YES)
    def test_clear_history_failure(self, message_box, speak):
        self.dialog.historyList.Set(["saved"])
        self.history.clear.return_value = None
        self.dialog.onClearHistory()
        assert self.dialog.historyList.GetCount() == 1
        speak.assert_called_once_with(
            _("Unable to clear search history"), interrupt=True
        )

    def test_empty_search_and_cancel_do_not_save(self):
        self.dialog.onSearch()
        assert not self.dialog._closing
        self.dialog.searchField.SetValue("not submitted")
        self.dialog.onClose()
        self.history.add.assert_not_called()
        assert self.dialog.query is None

    @patch("gui.search_dialog.speak")
    def test_save_failure_still_searches(self, speak):
        self.history.add.return_value = None
        self.dialog.searchField.SetValue("  query  ")
        self.dialog.onSearch()
        assert self.dialog.query == "query"
        self.history.add.assert_called_once_with("query")
        speak.assert_called_once_with(
            _("Unable to save search history"), interrupt=True
        )

    def test_initial_structure_and_accessibility(self):
        assert hasattr(self.dialog, "searchField")
        assert hasattr(self.dialog, "suggestionsList")
        assert hasattr(self.dialog, "filterBox")
        assert hasattr(self.dialog, "searchButton")
        assert hasattr(self.dialog, "closeButton")
        assert hasattr(self.dialog, "debounceTimer")

        # Accessibility names
        assert self.dialog.searchField.GetName() == _("ابحث في youtube")
        assert self.dialog.suggestionsList.GetName() == _("اقتراحات البحث")
        assert self.dialog.filterBox.GetName() == _("فلتر")

        # Suggestions should be hidden initially
        assert not self.dialog.suggestionsList.IsShown()
        assert not self.dialog.searchButton.IsEnabled()

    def test_text_change_starts_timer(self):
        self.dialog.searchField.SetValue("python")
        self.dialog.onTextChange(None)
        assert self.dialog.searchButton.IsEnabled()
        assert self.dialog.debounceTimer.IsRunning()

        # Emptying text stops timer and disables search
        self.dialog.searchField.SetValue("")
        self.dialog.onTextChange(None)
        assert not self.dialog.searchButton.IsEnabled()
        assert not self.dialog.debounceTimer.IsRunning()

    @patch("gui.search_dialog.speak")
    def test_suggestions_loaded_and_spoken(self, mock_speak):
        self.dialog.searchField.SetValue("python")
        self.dialog._request_counter = 1

        self.dialog._on_suggestions_loaded(
            "python", ["python tutorial", "python for beginners"], 1
        )

        assert self.dialog.suggestionsList.IsShown()
        assert self.dialog.suggestionsList.GetCount() == 2
        assert self.dialog.suggestionsList.GetString(0) == "python tutorial"
        assert self.dialog.suggestionsList.GetString(1) == "python for beginners"

        mock_speak.assert_called_once_with(_("تم عرض اقتراحات البحث"), interrupt=False)

    def test_stale_suggestions_ignored(self):
        self.dialog.searchField.SetValue("python 3")
        self.dialog._request_counter = 2

        # Old request id
        self.dialog._on_suggestions_loaded("python", ["python old"], 1)
        assert not self.dialog.suggestionsList.IsShown()

        # Mismatched query
        self.dialog._on_suggestions_loaded("python 2", ["python 2"], 2)
        assert not self.dialog.suggestionsList.IsShown()

    def test_typing_hides_existing_suggestions(self):
        # Manually show suggestions
        self.dialog.suggestionsList.Set(["suggestion 1"])
        self.dialog.suggestionsList.Show(True)
        assert self.dialog.suggestionsList.IsShown()

        # Typing modifies field and should hide existing suggestions
        self.dialog.searchField.SetValue("new text")
        self.dialog.onTextChange(None)
        assert not self.dialog.suggestionsList.IsShown()

    def test_select_suggestion_via_enter(self):
        self.dialog.suggestionsList.Set(["suggestion 1", "suggestion 2"])
        self.dialog.suggestionsList.SetSelection(1)

        event = MockKeyEvent(wx.WXK_RETURN)
        self.dialog.onSuggestionsKeyDown(event)

        assert self.dialog.query == "suggestion 2"
        assert self.dialog._closing is True

    def test_select_suggestion_via_dclick(self):
        self.dialog.suggestionsList.Set(["item 1", "item 2"])
        self.dialog.suggestionsList.SetSelection(0)

        self.dialog.onSuggestionsDClick(MagicMock())

        assert self.dialog.query == "item 1"
        assert self.dialog._closing is True

    def test_select_suggestion_via_right_arrow(self):
        self.dialog.suggestionsList.Set(["item 1", "item 2"])
        self.dialog.suggestionsList.SetSelection(1)
        self.dialog.suggestionsList.Show(True)

        event = MockKeyEvent(wx.WXK_RIGHT)
        self.dialog.onSuggestionsKeyDown(event)

        assert self.dialog.searchField.GetValue() == "item 2"
        assert not self.dialog.suggestionsList.IsShown()
        assert self.dialog._closing is False
        assert self.dialog.searchButton.IsEnabled()

    @patch("gui.search_dialog.config_get", return_value=False)
    def test_search_suggestions_disabled_by_setting(self, mock_config):
        self.dialog.searchField.SetValue("python")
        self.dialog.onTextChange(None)

        assert not self.dialog.debounceTimer.IsRunning()
        assert not self.dialog.suggestionsList.IsShown()

    def test_select_suggestion_via_click(self):
        self.dialog.suggestionsList.Set(["clicked item"])
        # Mock HitTest returning 0
        with patch.object(self.dialog.suggestionsList, "HitTest", return_value=0):
            event = MockMouseEvent(wx.Point(10, 10))
            self.dialog.onSuggestionsLeftUp(event)

        assert self.dialog.query == "clicked item"
        assert self.dialog._closing is True

    def test_keyboard_navigation_down_to_suggestions(self):
        self.dialog.suggestionsList.Set(["suggestion 1"])
        self.dialog.suggestionsList.Show(True)

        event = MockKeyEvent(wx.WXK_DOWN)
        self.dialog.onSearchFieldKeyDown(event)

        assert self.dialog.suggestionsList.GetSelection() == 0

    def test_keyboard_navigation_up_to_search_field(self):
        self.dialog.suggestionsList.Set(["suggestion 1", "suggestion 2"])
        self.dialog.suggestionsList.SetSelection(0)

        event = MockKeyEvent(wx.WXK_UP)
        self.dialog.onSuggestionsKeyDown(event)

        # Event was handled (not skipped), so focus returned to searchField
        assert event.skipped is False

    def test_escape_dismisses_suggestions_first(self):
        self.dialog.suggestionsList.Set(["suggestion 1"])
        self.dialog.suggestionsList.Show(True)

        event = MockKeyEvent(wx.WXK_ESCAPE)
        self.dialog.onCharHook(event)

        # Suggestions should be hidden and event handled without closing dialog
        assert not self.dialog.suggestionsList.IsShown()
        assert event.skipped is False

    def test_escape_skips_when_suggestions_hidden(self):
        assert not self.dialog.suggestionsList.IsShown()

        event = MockKeyEvent(wx.WXK_ESCAPE)
        self.dialog.onCharHook(event)

        # When hidden, event is skipped so dialog can close
        assert event.skipped is True
