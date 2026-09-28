import time
from unittest.mock import MagicMock, patch

from media_player.media_gui import MediaGui
from media_player.player import Player, State


def _make_gui():
    """A bare MediaGui with only the sleep-timer state the handlers touch."""
    gui = MediaGui.__new__(MediaGui)
    gui.sleep_timer = MagicMock()
    gui.sleep_timer.IsRunning.return_value = False
    gui.sleep_deadline = None
    gui.sleep_minutes = None
    gui.sleep_finish_current = False
    gui._sync_sleep_menu = MagicMock()
    return gui


def test_set_sleep_timer_arms_deadline_minutes_and_persists():
    gui = _make_gui()
    with (
        patch("media_player.media_gui.speak"),
        patch("media_player.media_gui.config_set") as mock_config_set,
    ):
        before = time.monotonic()
        gui.set_sleep_timer(30)

    assert gui.sleep_minutes == 30
    assert gui.sleep_finish_current is False
    assert gui.sleep_deadline is not None
    # Deadline is ~30 minutes out (allow slack for test execution time).
    assert 30 * 60 - 5 <= gui.sleep_deadline - before <= 30 * 60 + 5
    gui.sleep_timer.StartOnce.assert_called_once_with(30 * 60 * 1000)
    mock_config_set.assert_called_once_with("sleep_timer_last_minutes", 30)
    gui._sync_sleep_menu.assert_called_once()


def test_set_sleep_timer_zero_disarms_and_clears_finish():
    gui = _make_gui()
    gui.sleep_minutes = 30
    gui.sleep_deadline = time.monotonic() + 100
    gui.sleep_finish_current = True
    gui.sleep_timer.IsRunning.return_value = True

    with (
        patch("media_player.media_gui.speak"),
        patch("media_player.media_gui.config_set") as mock_config_set,
    ):
        gui.set_sleep_timer(0)

    assert gui.sleep_minutes is None
    assert gui.sleep_deadline is None
    assert gui.sleep_finish_current is False
    gui.sleep_timer.Stop.assert_called_once()
    gui.sleep_timer.StartOnce.assert_not_called()
    mock_config_set.assert_not_called()


def test_on_sleep_finish_current_sets_flag_and_clears_deadline():
    gui = _make_gui()
    gui.sleep_minutes = 30
    gui.sleep_deadline = time.monotonic() + 100

    with patch("media_player.media_gui.speak"):
        gui.on_sleep_finish_current()

    assert gui.sleep_finish_current is True
    assert gui.sleep_minutes is None
    assert gui.sleep_deadline is None
    gui._sync_sleep_menu.assert_called_once()


def _make_pause_gui(state, is_live):
    gui = MediaGui.__new__(MediaGui)
    gui.is_live = is_live
    gui.player = MagicMock()
    gui.player.media.get_state.return_value = state
    return gui


def test_sleep_pause_now_pauses_only_when_playing():
    gui = _make_pause_gui(State.Playing, is_live=False)
    with patch("media_player.media_gui.speak") as mock_speak:
        gui._sleep_pause_now()
    gui.player.media.pause.assert_called_once()
    gui.player.media.stop.assert_not_called()
    mock_speak.assert_called_once()


def test_sleep_pause_now_stops_when_live():
    gui = _make_pause_gui(State.Playing, is_live=True)
    with patch("media_player.media_gui.speak"):
        gui._sleep_pause_now()
    gui.player.media.stop.assert_called_once()
    gui.player.media.pause.assert_not_called()


def test_sleep_pause_now_noop_when_paused():
    gui = _make_pause_gui(State.Paused, is_live=False)
    with patch("media_player.media_gui.speak") as mock_speak:
        gui._sleep_pause_now()
    gui.player.media.pause.assert_not_called()
    gui.player.media.stop.assert_not_called()
    mock_speak.assert_not_called()


def test_sleep_pause_now_noop_without_player():
    gui = MediaGui.__new__(MediaGui)
    gui.player = None
    with patch("media_player.media_gui.speak") as mock_speak:
        # @has_player short-circuits to None; must not raise.
        assert gui._sleep_pause_now() is None
    mock_speak.assert_not_called()


def test_announce_sleep_remaining_finish_branch():
    gui = _make_gui()
    gui.sleep_finish_current = True
    with patch("media_player.media_gui.speak") as mock_speak:
        gui.announce_sleep_remaining()
    mock_speak.assert_called_once()


def test_announce_sleep_remaining_disarmed_branch():
    gui = _make_gui()
    with patch("media_player.media_gui.speak") as mock_speak:
        gui.announce_sleep_remaining()
    mock_speak.assert_called_once()


def test_announce_sleep_remaining_armed_branch():
    gui = _make_gui()
    gui.sleep_deadline = time.monotonic() + 120
    with patch("media_player.media_gui.speak") as mock_speak:
        gui.announce_sleep_remaining()
    mock_speak.assert_called_once()


def test_sync_sleep_menu_checks_matching_radio_item():
    gui = MediaGui.__new__(MediaGui)
    gui.sleepOffItem = MagicMock()
    gui.sleep15Item = MagicMock()
    gui.sleep30Item = MagicMock()
    gui.sleep45Item = MagicMock()
    gui.sleep60Item = MagicMock()
    gui.sleepFinishItem = MagicMock()
    gui.sleepCustomItem = MagicMock()

    gui.sleep_finish_current = True
    gui.sleep_minutes = None
    gui._sync_sleep_menu()
    gui.sleepFinishItem.Check.assert_called_once_with(True)

    gui.sleep_finish_current = False
    gui.sleep_minutes = None
    gui._sync_sleep_menu()
    gui.sleepOffItem.Check.assert_called_once_with(True)

    gui.sleep_minutes = 30
    gui._sync_sleep_menu()
    gui.sleep30Item.Check.assert_called_once_with(True)

    gui.sleep_minutes = 17  # non-preset -> custom
    gui._sync_sleep_menu()
    gui.sleepCustomItem.Check.assert_called_once_with(True)


def _make_player(window):
    p = Player.__new__(Player)
    p._closing = False
    p.do_reset = True
    p.media = MagicMock()
    p.media.get_media.return_value = object()
    p.apply_saved_audio_output_device = MagicMock()
    p.window = window
    return p


def test_reset_finish_current_stops_without_advancing_or_replaying():
    window = MagicMock()
    window.sleep_finish_current = True
    window.shorts_mode = False
    p = _make_player(window)

    # autonext + repeat forced True: without the finish-current guard this would
    # both replay and advance. The guard must pre-empt all of it.
    config = {"repeatTracks": True, "autonext": True}
    with (
        patch("media_player.player.wx.CallAfter") as mock_call_after,
        patch(
            "media_player.player.config_get", side_effect=lambda k: config.get(k, False)
        ),
    ):
        p.reset()

    mock_call_after.assert_called_once_with(window._on_sleep_finish_reached)
    p.media.play.assert_not_called()
    window.next.assert_not_called()


def test_reset_without_finish_current_still_advances_on_autonext():
    window = MagicMock()
    window.sleep_finish_current = False
    window.shorts_mode = False
    p = _make_player(window)

    config = {"repeatTracks": False, "autonext": True}
    with (
        patch("media_player.player.wx.CallAfter") as mock_call_after,
        patch(
            "media_player.player.config_get", side_effect=lambda k: config.get(k, False)
        ),
    ):
        p.reset()

    mock_call_after.assert_called_once_with(window.next)
    p.media.play.assert_not_called()
