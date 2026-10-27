from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import wx

from youtube_browser import browser as browser_module
from youtube_browser.browser import YoutubeBrowser


@pytest.fixture
def browser(monkeypatch):
    instance = YoutubeBrowser.__new__(YoutubeBrowser)
    wx.Frame.__init__(instance, None)
    instance._closing = False
    instance._request_generation = 0
    instance._search_future = None
    instance._load_more_future = None
    instance._loading_more = False
    instance._has_more = True
    instance.search = None
    instance.scraper = Mock()
    instance.searchResults = wx.ListBox(instance)
    instance.loadMoreButton = wx.Button(instance)
    instance.favCheck = wx.CheckBox(instance)
    instance.toggleControls = Mock()
    instance.on_search_complete = Mock()
    submissions = []
    callbacks = []

    def submit(coro):
        coro.close()
        future = Future()
        submissions.append(future)
        return future

    monkeypatch.setattr(browser_module, "submit_async", submit)
    monkeypatch.setattr(
        browser_module.wx, "CallAfter", lambda *args: callbacks.append(args)
    )
    monkeypatch.setattr(browser_module, "speak", Mock())
    monkeypatch.setattr(browser_module.utils, "show_error", Mock())
    monkeypatch.setattr(
        browser_module,
        "SearchDialog",
        Mock(return_value=SimpleNamespace(query="query", filter=0)),
    )
    instance.submissions = submissions
    instance.callbacks = callbacks
    return instance


def deliver(callbacks):
    for callback, *args in callbacks:
        callback(*args)
    callbacks.clear()


def test_old_search_response_cannot_replace_new_search(browser):
    browser.searchAction()
    old = Mock(name="old search")
    browser.submissions[0].set_result(old)
    assert browser.search is None  # UI updates are marshalled, not inline.
    browser.searchAction()
    new = Mock(name="new search")
    browser.submissions[1].set_result(new)
    deliver(browser.callbacks)
    assert browser.search is new
    browser.on_search_complete.assert_called_once()


def test_new_search_cancels_inflight_search_and_pagination(browser):
    browser.searchAction()
    first = browser.submissions[0]
    page = Future()
    browser._load_more_future = page
    browser._loading_more = True
    browser.searchAction()
    assert first.cancelled()
    assert page.cancelled()
    assert not browser._loading_more
    assert not browser.callbacks


def test_repeated_load_more_has_only_one_request_and_preserves_selection(browser):
    browser.search = SimpleNamespace(
        load_more=AsyncMock(),
        get_last_titles=lambda: ["second"],
        count=2,
        new_videos=1,
    )
    browser.searchResults.Set(["first"])
    browser.searchResults.SetSelection(0)
    for _ in range(100):
        browser.loadMore()
    assert len(browser.submissions) == 1
    assert browser._loading_more
    assert not browser.loadMoreButton.Enabled
    browser.submissions[0].set_result(True)
    deliver(browser.callbacks)
    assert not browser._loading_more
    assert browser.searchResults.Items == ["first", "second"]
    assert browser.searchResults.Selection == 0
    browser.searchResults.SetFocus.assert_not_called()


def test_old_page_response_cannot_append_to_new_search(browser):
    browser.search = SimpleNamespace(load_more=AsyncMock())
    browser.loadMore()
    browser.submissions[0].set_result(True)
    browser.searchAction()
    deliver(browser.callbacks)
    assert browser.searchResults.GetCount() == 0
    assert browser.search is None
    assert not browser._loading_more


def test_pagination_failure_allows_retry_on_gui_thread(browser):
    browser.search = SimpleNamespace(load_more=AsyncMock())
    browser.loadMore()
    browser.submissions[0].set_exception(RuntimeError("offline"))
    browser_module.utils.show_error.assert_not_called()
    deliver(browser.callbacks)
    assert not browser._loading_more
    assert browser.loadMoreButton.Enabled
    browser_module.utils.show_error.assert_called_once()
    browser.loadMore()
    assert len(browser.submissions) == 2


def test_no_more_pages_does_not_repeat_requests(browser):
    browser.search = SimpleNamespace(load_more=AsyncMock())
    browser.loadMore()
    browser.submissions[0].set_result(False)
    deliver(browser.callbacks)
    for _ in range(100):
        browser.loadMore()
    assert len(browser.submissions) == 1
    assert not browser.loadMoreButton.Enabled


def test_queued_completion_after_close_is_ignored(browser):
    browser.searchAction()
    browser.submissions[0].set_result(Mock())
    browser._close_requests()
    deliver(browser.callbacks)
    assert browser.search is None
    browser.on_search_complete.assert_not_called()
    browser.scraper.close.assert_called_once()
    browser._close_requests()
    browser.scraper.close.assert_called_once()


def test_background_submit_failure_is_reported_without_leaking_coroutine(
    browser, monkeypatch
):
    def fail(coro):
        coro.close()
        raise RuntimeError("loop unavailable")

    monkeypatch.setattr(browser_module, "submit_async", fail)
    browser.search = SimpleNamespace(load_more=AsyncMock())
    browser.loadMore()
    assert not browser._loading_more
    browser_module.utils.show_error.assert_called_once()
