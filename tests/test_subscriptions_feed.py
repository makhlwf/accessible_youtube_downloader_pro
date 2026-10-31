from unittest.mock import MagicMock, patch

import pytest
import wx

from accessible_youtube_downloader_pro import HomeScreen
from gui.subscriptions_feed import SubscriptionsFeed


def video(number, published="2 hours ago"):
    return {
        "id": str(number),
        "title": f"Video {number}",
        "author": "Channel",
        "url": f"https://www.youtube.com/watch?v={number}",
        "published_time": published,
    }


@pytest.fixture
def feed():
    with (
        patch("gui.subscriptions_feed.Thread") as thread,
        patch("gui.subscriptions_feed.Scraper"),
        patch("gui.subscriptions_feed.speak"),
    ):
        parent = wx.Frame(None)
        trigger = wx.Button(parent, label="Subscriptions feed")
        dialog = SubscriptionsFeed(parent, return_focus=trigger)
        yield dialog, thread, trigger
        dialog.back()


def apply(dialog, videos, continuation=None, load_more=False):
    dialog._apply_feed(
        dialog._request_id, {"videos": videos, "continuation": continuation}, load_more
    )


def test_home_feed_button_auth_visibility():
    with patch(
        "accessible_youtube_downloader_pro.utils.has_cookies_file", return_value=True
    ):
        home = HomeScreen(start_hidden=True)
        assert home.subscriptionsFeedBtn.IsShown()
        assert home.subscriptionsFeedBtn.GetName() == "Subscriptions feed"
        home.subscriptionsFeedItem.Enable.assert_called_with(True)
    with patch(
        "accessible_youtube_downloader_pro.utils.has_cookies_file", return_value=False
    ):
        home.update_shorts_button_visibility()
        assert not home.subscriptionsFeedBtn.IsShown()
        home.subscriptionsFeedItem.Enable.assert_called_with(False)
    home.Destroy()


def test_home_missing_cookies_does_not_open_feed():
    home = MagicMock()
    with (
        patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=False,
        ),
        patch("accessible_youtube_downloader_pro.utils.show_error") as error,
        patch("accessible_youtube_downloader_pro.speak") as speak,
        patch("gui.subscriptions_feed.SubscriptionsFeed") as constructor,
    ):
        HomeScreen.on_open_subscriptions_feed(home)
        constructor.assert_not_called()
        error.assert_called_once()
        assert speak.call_args.kwargs["interrupt"] is True


def test_home_opens_feed_with_return_target():
    home = MagicMock()
    with (
        patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=True,
        ),
        patch(
            "accessible_youtube_downloader_pro.utils.ensure_deno_installed",
            return_value=True,
        ),
        patch("gui.subscriptions_feed.SubscriptionsFeed") as constructor,
    ):
        HomeScreen.on_open_subscriptions_feed(home)
        constructor.assert_called_once_with(
            home, return_focus=home.subscriptionsFeedBtn
        )


def test_loading_has_named_list_and_disabled_actions(feed):
    dialog, thread, _ = feed
    assert dialog.videosList.GetName() == "Subscription videos, newest first"
    assert dialog.videosList.HasFocus()
    assert not dialog.playButton.IsEnabled()
    assert not dialog.videoButton.IsEnabled()
    assert not dialog.loadMoreButton.IsEnabled()
    assert not dialog.refreshButton.IsEnabled()
    assert dialog.backButton.IsEnabled()
    thread.assert_called_once()


def test_worker_only_dispatches_result_through_callafter(feed):
    dialog, thread, _ = feed
    response = {"videos": [video(1)], "continuation": "next"}
    with (
        patch(
            "gui.subscriptions_feed.utils.get_subscriptions_feed", return_value=response
        ) as fetch,
        patch("gui.subscriptions_feed.wx.CallAfter") as dispatch,
    ):
        thread.call_args.kwargs["target"]()
        fetch.assert_called_once_with(None)
        dispatch.assert_called_once_with(
            dialog._apply_feed, dialog._request_id, response, False
        )
        assert dialog.videos == []


def test_worker_exception_is_sanitized_and_dispatched(feed):
    _dialog, thread, _ = feed
    with (
        patch(
            "gui.subscriptions_feed.utils.get_subscriptions_feed",
            side_effect=RuntimeError("secret"),
        ),
        patch("gui.subscriptions_feed.wx.CallAfter") as dispatch,
    ):
        thread.call_args.kwargs["target"]()
        assert "secret" not in str(dispatch.call_args)
        assert dispatch.call_args.args[2].get("error")


def test_feed_preserves_chronological_service_order_and_published_text(feed):
    dialog, _, _ = feed
    apply(
        dialog,
        [video(3, "1 hour ago"), video(2, "2 hours ago"), video(1, "Yesterday")],
        "next",
    )
    assert [item["id"] for item in dialog.videos] == ["3", "2", "1"]
    assert (
        dialog.videosList.Items[0] == "Video 3, channel: Channel, published: 1 hour ago"
    )
    assert dialog.videosList.GetSelection() == 0
    assert dialog.playButton.IsEnabled()
    assert dialog.loadMoreButton.IsEnabled()


def test_load_more_deduplicates_and_preserves_selection_and_focus(feed):
    dialog, thread, _ = feed
    apply(dialog, [video(3), video(2)], "next")
    dialog.videosList.SetSelection(1)
    dialog.loadMoreButton.SetFocus()
    dialog.load_feed(True)
    assert dialog.videosList.HasFocus()
    assert not dialog.loadMoreButton.IsEnabled()
    with (
        patch(
            "gui.subscriptions_feed.utils.get_subscriptions_feed", return_value={}
        ) as fetch,
        patch("gui.subscriptions_feed.wx.CallAfter"),
    ):
        thread.call_args.kwargs["target"]()
        fetch.assert_called_once_with("next")
    # Moving to Back while the network runs must not be undone on completion.
    dialog.backButton.SetFocus()
    apply(dialog, [video(2), video(1)], load_more=True)
    assert [item["id"] for item in dialog.videos] == ["3", "2", "1"]
    assert dialog.videosList.GetSelection() == 1
    assert dialog.backButton.HasFocus()
    assert not dialog.loadMoreButton.IsEnabled()
    assert "End of subscriptions feed" in dialog.status.GetLabel()


def test_duplicate_requests_and_no_continuation_are_ignored(feed):
    dialog, thread, _ = feed
    dialog.load_feed()
    dialog.load_feed(True)
    assert thread.call_count == 1
    apply(dialog, [video(1)])
    dialog.load_feed(True)
    assert thread.call_count == 1


def test_empty_feed_never_activates_placeholder(feed):
    dialog, _, _ = feed
    apply(dialog, [])
    assert dialog.videosList.Items == []
    assert not dialog.playButton.IsEnabled()
    assert "No videos" in dialog.status.GetLabel()
    with patch("gui.subscriptions_feed.LoadingDialog") as loading:
        dialog.play()
        loading.assert_not_called()


def test_page_failure_keeps_items_and_token_for_retry(feed):
    dialog, _, _ = feed
    apply(dialog, [video(2)], "page-two")
    dialog.load_feed(True)
    dialog._apply_feed(dialog._request_id, {"error": "Try again"}, True)
    assert [item["id"] for item in dialog.videos] == ["2"]
    assert dialog.continuation == "page-two"
    assert dialog.loadMoreButton.IsEnabled()
    assert dialog.refreshButton.IsEnabled()
    assert dialog.status.GetLabel() == "Try again"


def test_refresh_replaces_feed_and_retains_selected_video(feed):
    dialog, _, _ = feed
    apply(dialog, [video(2), video(1)], "old")
    dialog.load_feed()
    apply(dialog, [video(3), video(2)], "new")
    assert [item["id"] for item in dialog.videos] == ["3", "2"]
    assert dialog.videosList.GetSelection() == 1
    assert dialog.continuation == "new"


def test_repeated_continuation_stops_paging(feed):
    dialog, _, _ = feed
    apply(dialog, [video(2)], "same")
    dialog.load_feed(True)
    apply(dialog, [video(2)], "same", load_more=True)
    assert dialog.continuation is None
    assert not dialog.loadMoreButton.IsEnabled()


def test_escape_closes_and_restores_trigger_focus(feed):
    dialog, _, trigger = feed
    event = MagicMock(KeyCode=wx.WXK_ESCAPE)
    dialog.on_key(event)
    assert dialog._closed
    assert trigger.HasFocus()
    assert dialog.Parent.IsShown()
    dialog.scraper.close.assert_called()


def test_late_or_stale_result_cannot_touch_controls(feed):
    dialog, _, _ = feed
    request_id = dialog._request_id
    dialog._apply_feed(request_id - 1, {"videos": [video(1)]})
    assert dialog.videos == []
    dialog.back()
    dialog.videosList.Set = MagicMock()
    with patch("gui.subscriptions_feed.speak") as speak:
        dialog._apply_feed(request_id, {"videos": [video(1)]})
        dialog.videosList.Set.assert_not_called()
        speak.assert_not_called()


@pytest.mark.parametrize("control,audio_mode", [(False, True), (True, False)])
def test_list_enter_plays_expected_mode(feed, control, audio_mode):
    dialog, _, _ = feed
    apply(dialog, [video(1)])
    dialog.videosList.SetFocus()
    event = MagicMock(KeyCode=wx.WXK_RETURN)
    event.ControlDown.return_value = control
    with patch.object(dialog, "play") as play:
        dialog.on_key(event)
        play.assert_called_once_with(audio_mode=audio_mode)


def test_button_enter_is_not_swallowed(feed):
    dialog, _, _ = feed
    dialog.backButton.SetFocus()
    event = MagicMock(KeyCode=wx.WXK_RETURN)
    dialog.on_key(event)
    event.Skip.assert_called_once()


def test_play_uses_existing_player_and_results(feed):
    dialog, _, _ = feed
    apply(dialog, [video(1)])
    stream = MagicMock()
    dialog.results.set_stream(0, stream, audio_mode=True)
    with patch("media_player.media_gui.MediaGui") as player:
        dialog.play(True)
        player.assert_called_once_with(
            dialog,
            "Video 1",
            stream,
            video(1)["url"],
            audio_mode=True,
            results=dialog.results,
        )
        assert not dialog.IsShown()


def test_missing_published_time_is_explicit():
    label = SubscriptionsFeed._video_label({"title": "Video", "author": "Channel"})
    assert "Publication time unavailable" in label


def test_empty_page_with_token_remains_navigable(feed):
    dialog, _, _ = feed
    apply(dialog, [], "older-videos")
    assert dialog.loadMoreButton.IsEnabled()
    assert not dialog.playButton.IsEnabled()
    assert dialog.status.GetLabel() == "No videos on this page. Load more to continue."


def test_malformed_response_is_retryable(feed):
    dialog, _, _ = feed
    dialog._apply_feed(dialog._request_id, {"videos": None})
    assert not dialog._loading
    assert dialog.refreshButton.IsEnabled()
    assert "Could not load" in dialog.status.GetLabel()


def test_native_destroy_ignores_child_but_cancels_frame(feed):
    dialog, _, _ = feed
    event = MagicMock()
    event.GetEventObject.return_value = dialog.videosList
    dialog.on_destroy(event)
    assert not dialog._closed
    event.GetEventObject.return_value = dialog
    dialog.on_destroy(event)
    assert dialog._closed
    dialog.scraper.close.assert_called_once()


def test_keyboard_shortcut_and_button_menu_bindings():
    with patch(
        "accessible_youtube_downloader_pro.utils.has_cookies_file", return_value=True
    ):
        home = HomeScreen(start_hidden=True)
    bindings = home.Bind.call_args_list
    assert any(
        call.args[1:] == (home.on_open_subscriptions_feed, home.subscriptionsFeedItem)
        for call in bindings
    )
    home.subscriptionsFeedBtn.Bind.assert_called_once_with(
        wx.EVT_BUTTON, home.on_open_subscriptions_feed
    )
    # The accelerator must be independent of the existing subscribed-channels shortcut.
    shortcut_entries = wx.AcceleratorTable.call_args.args[0]
    assert (
        wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
        ord("N"),
        home.subscriptionsFeedItem.GetId(),
    ) in shortcut_entries
    home.Destroy()


def test_declined_playback_dependency_announces_terminal_state(feed):
    dialog, _, _ = feed
    apply(dialog, [video(1)])
    dialog.playButton.SetFocus()
    with (
        patch("gui.subscriptions_feed.utils.check_yt_dlp", return_value=False),
        patch("gui.subscriptions_feed.LoadingDialog") as loading,
        patch("gui.subscriptions_feed.speak") as speak,
    ):
        dialog.play(True)
        assert dialog.status.GetLabel() == "Playback was not started."
        speak.assert_called_with("Playback was not started.", interrupt=True)
        loading.assert_not_called()
        assert dialog.videosList.HasFocus()
        assert dialog.IsShown()
