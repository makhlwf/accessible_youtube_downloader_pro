from unittest.mock import Mock

import pytest

from gui import search_dialog


@pytest.fixture
def dialog(monkeypatch):
    history = Mock()
    history.get_recent.return_value = []
    monkeypatch.setattr(search_dialog, "SearchHistory", history)
    monkeypatch.setattr(search_dialog, "config_get", lambda key: True)
    monkeypatch.setattr(search_dialog, "speak", Mock())
    monkeypatch.setattr(search_dialog.threading, "Thread", Mock())
    instance = search_dialog.SearchDialog(None, show_modal=False)
    yield instance
    instance.onClose()


def query(dialog, text):
    dialog.searchField.SetValue(text)
    dialog.onTextChange(None)
    dialog.onDebounceTimer(None)
    return dialog._request_counter


def test_only_latest_debounced_suggestion_waits_behind_active_request(dialog):
    first_id = query(dialog, "first")
    for number in range(100):
        query(dialog, f"query {number}")
    assert search_dialog.threading.Thread.call_count == 1
    assert dialog._pending_suggestion == ("query 99", dialog._request_counter)
    dialog._on_suggestions_finished("first", ["old"], first_id)
    assert search_dialog.threading.Thread.call_count == 2
    assert search_dialog.threading.Thread.call_args.kwargs["args"] == (
        "query 99",
        dialog._request_counter,
    )
    assert not dialog.suggestionsList.IsShown()
    dialog._on_suggestions_finished("query 99", ["latest"], dialog._request_counter)
    assert dialog.suggestionsList.Items == ["latest"]
    assert not dialog._suggestions_inflight


def test_typing_invalidates_same_query_before_next_debounce(dialog):
    old_id = query(dialog, "same")
    dialog.searchField.SetValue("changed")
    dialog.onTextChange(None)
    dialog.searchField.SetValue("same")
    dialog.onTextChange(None)
    dialog._on_suggestions_finished("same", ["stale"], old_id)
    assert not dialog.suggestionsList.IsShown()
    assert search_dialog.threading.Thread.call_count == 1


def test_close_drops_pending_query_and_queued_suggestions(dialog):
    old_id = query(dialog, "old")
    query(dialog, "new")
    dialog.onClose()
    dialog._on_suggestions_finished("old", ["stale"], old_id)
    assert search_dialog.threading.Thread.call_count == 1
    assert dialog._pending_suggestion is None
    assert not dialog.suggestionsList.IsShown()


def test_empty_query_discards_waiting_suggestion_request(dialog):
    old_id = query(dialog, "old")
    query(dialog, "new")
    dialog.searchField.SetValue("")
    dialog.onTextChange(None)
    dialog._on_suggestions_finished("old", ["stale"], old_id)
    assert dialog._pending_suggestion is None
    assert search_dialog.threading.Thread.call_count == 1
    assert not dialog.debounceTimer.IsRunning()
