from unittest.mock import MagicMock, patch

import pytest
import wx

from media_player.media_gui import MediaGui


@pytest.fixture(scope="module")
def wx_app():
    app = wx.App()
    yield app


def test_mediagui_has_suggestions_controls(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        assert hasattr(frame, "suggestions_list")
        assert hasattr(frame, "load_more_suggestions_btn")
        assert hasattr(frame, "suggestions_data")
        assert isinstance(frame.suggestions_list, wx.ListBox)
        assert frame.suggestions_list.GetName() == "suggestions_list"

        # Check fullscreen toggle hides suggestions
        frame.toggleFullScreen(True)
        assert not frame.suggestions_list.IsShown()
        assert not frame.load_more_suggestions_btn.IsShown()

        frame.toggleFullScreen(False)
        assert frame.suggestions_list.IsShown()


class MockKeyEvent:
    """Mock key event for testing keyboard navigation hooks."""

    def __init__(self, key_code, shift_down=False, ctrl_down=False, alt_down=False):
        self._key_code = key_code
        self._shift = shift_down
        self._ctrl = ctrl_down
        self._alt = alt_down
        self.skipped = None

    def GetKeyCode(self):
        return self._key_code

    def ShiftDown(self):
        return self._shift

    def ControlDown(self):
        return self._ctrl

    def AltDown(self):
        return self._alt

    def HasAnyModifiers(self):
        return self._shift or self._ctrl or self._alt

    def Skip(self, val=True):
        self.skipped = bool(val)


def test_escape_returns_focus_to_canvas(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        # Put focus on suggestions list
        frame.suggestions_list.SetFocus()

        # Simulate Escape key event
        event = MockKeyEvent(wx.WXK_ESCAPE)
        frame.on_suggestions_char_hook(event)

        # Focus should return to frame (canvas)
        assert frame.FindFocus() == frame
        frame.Destroy()


def test_escape_on_canvas_closes_player(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.SetFocus()
        with patch.object(frame, "closeAction") as mock_close:
            event = MockKeyEvent(wx.WXK_ESCAPE)
            frame.onCharHook(event)
            mock_close.assert_called_once()
        frame.Destroy()


def test_tab_from_canvas_moves_focus_to_suggestions(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.SetFocus()
        assert frame.FindFocus() == frame

        event = MockKeyEvent(wx.WXK_TAB, shift_down=False)
        frame.onCharHook(event)

        assert frame.FindFocus() == frame.suggestions_list
        frame.Destroy()


def test_shift_tab_from_suggestions_returns_focus_to_canvas(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_list.SetFocus()
        assert frame.FindFocus() == frame.suggestions_list

        event = MockKeyEvent(wx.WXK_TAB, shift_down=True)
        frame.on_suggestions_char_hook(event)

        assert frame.FindFocus() == frame
        frame.Destroy()


def test_suggestions_set_focus_selects_first_item_when_unset(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_list.Set(["Video 1", "Video 2"])
        frame.suggestions_list.SetSelection(wx.NOT_FOUND)

        event = MagicMock()
        frame.on_suggestions_set_focus(event)
        assert frame.suggestions_list.GetSelection() == 0

        # When selection is already set, it should not reset to 0
        frame.suggestions_list.SetSelection(1)
        frame.on_suggestions_set_focus(event)
        assert frame.suggestions_list.GetSelection() == 1

        # When items list is empty, selection remains NOT_FOUND
        frame.suggestions_list.Clear()
        frame.suggestions_list.SetSelection(wx.NOT_FOUND)
        frame.on_suggestions_set_focus(event)
        assert frame.suggestions_list.GetSelection() == wx.NOT_FOUND

        frame.Destroy()


def test_shift_tab_from_first_visible_control_moves_to_suggestions_or_load_more(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        # Case 1: _previous_button hidden, first visible control is beginingButton
        # load_more_suggestions_btn is hidden
        frame.load_more_suggestions_btn.Hide()
        first_ctrl = frame._get_first_visible_player_control()
        assert first_ctrl == frame._player_controls[1]
        first_ctrl.SetFocus()
        assert frame.FindFocus() == first_ctrl

        event = MockKeyEvent(wx.WXK_TAB, shift_down=True)
        frame.onCharHook(event)
        assert frame.FindFocus() == frame.suggestions_list

        # Case 2: load_more_suggestions_btn is shown
        frame.load_more_suggestions_btn.Show()
        first_ctrl.SetFocus()
        frame.onCharHook(event)
        assert frame.FindFocus() == frame.load_more_suggestions_btn

        # Case 3: _previous_button is shown (e.g. results present)
        frame._previous_button.Show(True)
        frame.load_more_suggestions_btn.Hide()
        first_ctrl = frame._get_first_visible_player_control()
        assert first_ctrl == frame._previous_button
        first_ctrl.SetFocus()
        frame.onCharHook(event)
        assert frame.FindFocus() == frame.suggestions_list

        frame.Destroy()


def test_tab_from_suggestions_list_forward_flow(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        # Case 1: load_more_suggestions_btn is shown
        frame.suggestions_list.SetFocus()
        frame.load_more_suggestions_btn.Show(True)
        event = MockKeyEvent(wx.WXK_TAB, shift_down=False)
        frame.onCharHook(event)
        assert frame.FindFocus() == frame.load_more_suggestions_btn

        # Case 2: load_more_suggestions_btn is hidden -> moves to first visible player control
        frame.suggestions_list.SetFocus()
        frame.load_more_suggestions_btn.Hide()
        first_ctrl = frame._get_first_visible_player_control()
        frame.onCharHook(event)
        assert frame.FindFocus() == first_ctrl

        frame.Destroy()


def test_set_player_controls_visible_handles_exceptions(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        with patch.object(
            frame.suggestions_list, "Show", side_effect=RuntimeError("Test error")
        ):
            frame._set_player_controls_visible(True)

        with patch.object(
            frame.suggestions_list, "Show", side_effect=AttributeError("Test error")
        ):
            frame._set_player_controls_visible(True)

        frame.Destroy()


def test_activate_suggestion_updates_results_and_calls_change_track(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {
                "id": "rel1",
                "title": "Related Video 1",
                "url": "https://www.youtube.com/watch?v=rel1",
                "duration": "04:20",
                "channel": {"name": "RelChannel", "url": ""},
            },
            {
                "id": "rel2",
                "title": "Related Video 2",
                "url": "https://www.youtube.com/watch?v=rel2",
                "duration": "05:10",
                "channel": {"name": "RelChannel 2", "url": ""},
            },
        ]
        frame.suggestions_list.Set(["Related Video 1", "Related Video 2"])
        frame.suggestions_list.SetSelection(1)

        with patch.object(frame, "changeTrack") as mock_change_track:
            frame.on_activate_suggestion(audio_mode=False)

            assert frame.results == frame.suggestions_data
            assert frame.current_index == 1
            mock_change_track.assert_called_once_with(1)
        frame.Destroy()


def test_activate_suggestion_audio_mode_and_invalid_index(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {"id": "v1", "title": "Video 1", "url": "https://url1"},
        ]
        frame.suggestions_list.Set(["Video 1"])

        # Test invalid index
        frame.suggestions_list.SetSelection(wx.NOT_FOUND)
        with patch.object(frame, "changeTrack") as mock_change_track:
            frame.on_activate_suggestion(audio_mode=True)
            mock_change_track.assert_not_called()

        # Test audio_mode=True
        frame.suggestions_list.SetSelection(0)
        with patch.object(frame, "changeTrack") as mock_change_track:
            frame.on_activate_suggestion(audio_mode=True)
            assert frame.audio_mode is True
            assert frame.results == frame.suggestions_data
            assert frame.current_index == 0
            assert frame._previous_button.IsShown()
            assert frame._next_button.IsShown()
            mock_change_track.assert_called_once_with(0)
        frame.Destroy()


def test_fetch_suggestions_initial_load_and_formatting(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
        patch(
            "media_player.media_gui.wx.CallAfter",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        fake_videos = [
            {
                "id": "v1",
                "title": "Video 1",
                "url": "https://www.youtube.com/watch?v=v1",
                "duration": "03:15",
                "channel": {"name": "Channel One", "url": "https://channel/1"},
            },
            {
                "id": "v2",
                "title": "Video 2",
                "url": "https://www.youtube.com/watch?v=v2",
                "duration": "",
                "channel": None,  # test None guard
            },
        ]
        with patch(
            "media_player.media_gui.SuggestionsService.fetch_related",
            return_value={"videos": fake_videos, "continuation": "token123"},
        ):
            frame.fetch_suggestions(load_more=False)

            assert len(frame.suggestions_data) == 2
            assert frame.suggestions_continuation == "token123"
            assert frame.load_more_suggestions_btn.IsShown()
            items = frame.suggestions_list.Items
            assert len(items) == 2
            assert "Video 1" in items[0]
            assert "03:15" in items[0]
            assert "Channel One" in items[0]
            assert "Video 2" in items[1]
        frame.Destroy()


def test_fetch_suggestions_load_more_extends_data(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
        patch(
            "media_player.media_gui.wx.CallAfter",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {
                "id": "v1",
                "title": "Video 1",
                "duration": "01:00",
                "channel": {"name": "C1"},
            }
        ]
        frame.suggestions_continuation = "token123"
        more_videos = [
            {
                "id": "v2",
                "title": "Video 2",
                "duration": "02:00",
                "channel": {"name": "C2"},
            }
        ]
        with patch(
            "media_player.media_gui.SuggestionsService.fetch_related",
            return_value={"videos": more_videos, "continuation": None},
        ) as mock_fetch:
            frame.fetch_suggestions(load_more=True)

            mock_fetch.assert_called_once_with(
                frame.url, limit=20, continuation="token123"
            )
            assert len(frame.suggestions_data) == 2
            assert frame.suggestions_continuation is None
            assert not frame.load_more_suggestions_btn.IsShown()
        frame.Destroy()


def test_fetch_suggestions_empty_and_error_handling(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
        patch(
            "media_player.media_gui.wx.CallAfter",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        # Empty result
        with patch(
            "media_player.media_gui.SuggestionsService.fetch_related",
            return_value={"videos": [], "continuation": None},
        ):
            frame.fetch_suggestions(load_more=False)
            items = frame.suggestions_list.Items
            assert len(items) == 1
            assert "لا تتوفر اقتراحات" in items[0]

        # Error result
        frame.suggestions_data = []
        with patch(
            "media_player.media_gui.SuggestionsService.fetch_related",
            side_effect=RuntimeError("Network failure"),
        ):
            frame.fetch_suggestions(load_more=False)
            items = frame.suggestions_list.Items
            assert len(items) == 1
            assert "تعذر تحميل الاقتراحات" in items[0]

        frame.Destroy()


def test_suggestions_key_events_enter_and_ctrl_enter(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_list.SetFocus()

        # Enter key -> on_activate_suggestion(audio_mode=False)
        with patch.object(frame, "on_activate_suggestion") as mock_activate:
            event_enter = MockKeyEvent(wx.WXK_RETURN, ctrl_down=False)
            frame.on_suggestions_char_hook(event_enter)
            mock_activate.assert_called_once_with(audio_mode=False)

        # Ctrl+Enter key -> on_activate_suggestion(audio_mode=True)
        with patch.object(frame, "on_activate_suggestion") as mock_activate:
            event_ctrl_enter = MockKeyEvent(wx.WXK_RETURN, ctrl_down=True)
            frame.on_suggestions_char_hook(event_ctrl_enter)
            mock_activate.assert_called_once_with(audio_mode=True)

        # on_suggestions_key_down Enter
        with patch.object(frame, "on_activate_suggestion") as mock_activate:
            event_enter = MockKeyEvent(wx.WXK_RETURN, ctrl_down=False)
            frame.on_suggestions_key_down(event_enter)
            mock_activate.assert_called_once_with(audio_mode=False)

        # on_suggestions_key_down Ctrl+Enter
        with patch.object(frame, "on_activate_suggestion") as mock_activate:
            event_ctrl_enter = MockKeyEvent(wx.WXK_RETURN, ctrl_down=True)
            frame.on_suggestions_key_down(event_ctrl_enter)
            mock_activate.assert_called_once_with(audio_mode=True)

        # Context menu key -> on_suggestions_context_menu
        with patch.object(frame, "on_suggestions_context_menu") as mock_cm:
            event_menu = MockKeyEvent(399)
            with patch.object(frame, "_is_context_menu_key", return_value=True):
                frame.on_suggestions_char_hook(event_menu)
                mock_cm.assert_called_once_with(event_menu)

        frame.Destroy()


def test_suggestions_context_menu_structure_and_actions(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {
                "id": "v1",
                "title": "Sug Title",
                "url": "https://www.youtube.com/watch?v=v1",
                "duration": "03:00",
                "channel": {"name": "Sug Channel", "url": "https://channel/sug"},
            }
        ]
        frame.suggestions_list.Set(["Sug Item"])
        frame.suggestions_list.SetSelection(0)

        menu = frame.create_suggestions_context_menu(0)
        assert menu is not None
        append_labels = [
            call.args[1] for call in menu.Append.call_args_list if len(call.args) > 1
        ]
        submenu_labels = [
            call.args[1]
            for call in menu.AppendSubMenu.call_args_list
            if len(call.args) > 1
        ]

        # Check presence of expected items
        assert any("تشغيل" in label for label in append_labels)
        assert any("صوتي" in label for label in append_labels)
        assert any("تنزيل" in label for label in submenu_labels)
        assert any("التنزيل المباشر" in label for label in append_labels)
        assert any("نسخ رابط" in label for label in append_labels)
        assert any("القناة" in label for label in append_labels)
        assert any("متصفح" in label for label in append_labels)
        menu.Destroy()
        frame.Destroy()


def test_on_suggestions_context_menu_calls_popup_menu(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [{"id": "v1", "title": "Sug 1", "url": "https://u1"}]
        frame.suggestions_list.Set(["Sug 1"])
        frame.suggestions_list.SetSelection(0)

        mock_popup = MagicMock()
        frame.suggestions_list.PopupMenu = mock_popup
        frame.on_suggestions_context_menu()
        mock_popup.assert_called_once()
        frame.Destroy()


def test_suggestions_list_double_click(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [{"id": "v1", "title": "Sug 1", "url": "https://u1"}]
        frame.suggestions_list.Set(["Sug 1"])
        frame.suggestions_list.SetSelection(0)

        with patch.object(frame, "on_activate_suggestion") as mock_activate:
            dclick_handlers = [
                call.args[1]
                for call in frame.suggestions_list.Bind.call_args_list
                if len(call.args) > 1 and call.args[0] == wx.EVT_LISTBOX_DCLICK
            ]
            assert len(dclick_handlers) == 1
            dclick_handlers[0](MagicMock())
            mock_activate.assert_called_once_with(audio_mode=False)

        frame.Destroy()


def test_load_more_suggestions_button_triggers_thread(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread") as mock_thread,
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.on_load_more_suggestions()
        mock_thread.assert_called()
        frame.Destroy()


def test_perform_track_change_triggers_fetch_suggestions(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread") as mock_thread,
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        mock_stream = MagicMock()
        mock_stream.url = "http://stream2"
        mock_stream.title = "New Track"
        mock_stream.headers = None
        mock_stream.audio_url = None

        targets = []

        def side_effect(*args, **kwargs):
            target = kwargs.get("target")
            if target:
                targets.append(target)
            return MagicMock()

        mock_thread.side_effect = side_effect
        frame._perform_track_change(
            mock_stream, "https://www.youtube.com/watch?v=new123", "New Track", 0
        )

        assert frame.fetch_suggestions in targets
        frame.Destroy()


def test_next_and_previous_navigate_suggestions_when_parent_has_search_results(
    wx_app,
):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
    ):
        mock_parent = MagicMock()
        mock_parent.searchResults = MagicMock()
        mock_parent.searchResults.Selection = 5

        frame = MediaGui(
            parent=mock_parent,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {"id": "v0", "title": "Track 0", "url": "https://url0"},
            {"id": "v1", "title": "Track 1", "url": "https://url1"},
            {"id": "v2", "title": "Track 2", "url": "https://url2"},
        ]
        frame.suggestions_list.Set(["Track 0", "Track 1", "Track 2"])
        frame.suggestions_list.SetSelection(1)

        with patch.object(frame, "changeTrack") as mock_change_track:
            frame.on_activate_suggestion(audio_mode=False, index=1)
            assert frame._suggestions_mode is True
            assert frame.current_index == 1
            mock_change_track.assert_called_with(1)

            # Test next()
            mock_change_track.reset_mock()
            frame.next()
            assert frame.current_index == 2
            mock_change_track.assert_called_once_with(2)
            assert mock_parent.searchResults.Selection == 5

            # Test boundary (end of suggestions list)
            mock_change_track.reset_mock()
            frame.next()
            assert frame.current_index == 2
            mock_change_track.assert_not_called()

            # Test previous()
            mock_change_track.reset_mock()
            frame.previous()
            assert frame.current_index == 1
            mock_change_track.assert_called_once_with(1)
            assert mock_parent.searchResults.Selection == 5

            # Test previous() to index 0
            mock_change_track.reset_mock()
            frame.previous()
            assert frame.current_index == 0
            mock_change_track.assert_called_once_with(0)

            # Test boundary (start of suggestions list)
            mock_change_track.reset_mock()
            frame.previous()
            assert frame.current_index == 0
            mock_change_track.assert_not_called()

        frame.Destroy()


def test_fetch_suggestions_load_more_appends_and_preserves_selection(wx_app):
    with (
        patch("media_player.media_gui.Player"),
        patch("media_player.media_gui.Thread"),
        patch(
            "media_player.media_gui.wx.CallAfter",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ),
    ):
        frame = MediaGui(
            parent=None,
            title="Test",
            stream=MagicMock(url="http://fake.stream"),
            url="https://www.youtube.com/watch?v=dummy123",
            can_download=True,
        )
        frame.suggestions_data = [
            {
                "id": "v1",
                "title": "Video 1",
                "duration": "01:00",
                "channel": {"name": "C1"},
            }
        ]
        frame.suggestions_list.Set(["Video 1"])
        frame.suggestions_list.SetSelection(0)
        frame.suggestions_continuation = "token123"

        more_videos = [
            {
                "id": "v2",
                "title": "Video 2",
                "duration": "02:00",
                "channel": {"name": "C2"},
            }
        ]
        with patch(
            "media_player.media_gui.SuggestionsService.fetch_related",
            return_value={"videos": more_videos, "continuation": None},
        ):
            frame.fetch_suggestions(load_more=True)

            assert len(frame.suggestions_data) == 2
            assert len(frame.suggestions_list.Items) == 2
            assert frame.suggestions_list.GetSelection() == 0
        frame.Destroy()
