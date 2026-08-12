from unittest.mock import MagicMock, patch

import wx

import utils
from accessible_youtube_downloader_pro import HomeScreen
from media_player.media_gui import MediaGui


def test_has_cookies_file_missing(tmp_path):
    with patch("utils.config_get", return_value=""):
        assert utils.has_cookies_file() is False

    with patch("utils.config_get", return_value=str(tmp_path / "non_existent.txt")):
        assert utils.has_cookies_file() is False


def test_has_cookies_file_valid(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSAPISID\t12345\n"
    )
    with patch("utils.config_get", return_value=str(cookie_file)):
        assert utils.has_cookies_file() is True


def test_get_shorts_feed_success(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("cookie_data")
    mock_response = {
        "shorts": [
            {
                "id": "short1",
                "title": "Short 1",
                "author": "Author 1",
                "url": "https://www.youtube.com/shorts/short1",
            },
            {
                "id": "short2",
                "title": "Short 2",
                "author": "Author 2",
                "url": "https://www.youtube.com/shorts/short2",
            },
        ]
    }
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
        patch("utils.config_get", return_value=str(cookie_file)),
        patch("utils.deno_service.send_command", return_value=mock_response),
    ):
        shorts = utils.get_shorts_feed()
        assert len(shorts) == 2
        assert shorts[0]["id"] == "short1"
        assert shorts[1]["id"] == "short2"


def test_get_shorts_feed_no_cookies():
    with patch("utils.ensure_cookies_configured", return_value=False):
        shorts = utils.get_shorts_feed()
        assert shorts == []


def test_home_screen_shorts_button_visibility(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("data")

    with (
        patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=True,
        ),
        patch(
            "accessible_youtube_downloader_pro.browser_extension_manager.sync_browser_extension_files"
        ),
    ):
        home = HomeScreen(start_hidden=True)
        assert home.shortsBtn.IsShown() is True
        home.shortsItem.Enable.assert_called_with(True)

        with patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=False,
        ):
            home.update_shorts_button_visibility()
            assert home.shortsBtn.IsShown() is False
            home.shortsItem.Enable.assert_called_with(False)


def test_media_gui_shorts_mode_key_events():
    mock_stream = MagicMock()
    mock_stream.url = "http://fake.stream/url"
    mock_stream.headers = {}
    mock_stream.audio_url = None

    shorts_list = [
        {
            "id": "short1",
            "title": "Short 1",
            "url": "https://www.youtube.com/shorts/short1",
        },
        {
            "id": "short2",
            "title": "Short 2",
            "url": "https://www.youtube.com/shorts/short2",
        },
        {
            "id": "short3",
            "title": "Short 3",
            "url": "https://www.youtube.com/shorts/short3",
        },
    ]

    with (
        patch("media_player.media_gui.Player"),
        patch(
            "media_player.media_gui.utils.get_playable_stream", return_value=mock_stream
        ),
        patch(
            "media_player.media_gui.utils.get_video_like_info",
            return_value={"likes": 10, "rating": None},
        ),
        patch("media_player.media_gui.speak"),
    ):
        gui = MediaGui(
            parent=None,
            title="Short 1",
            stream=mock_stream,
            url="https://www.youtube.com/shorts/short1",
            can_download=True,
            results=shorts_list,
            shorts_mode=True,
        )

        assert gui.shorts_mode is True
        assert gui.current_index == 0

        # Test Down Arrow -> Next Short
        down_evt = MagicMock()
        down_evt.GetKeyCode.side_effect = lambda: wx.WXK_DOWN
        down_evt.HasAnyModifiers.return_value = False
        down_evt.ShiftDown.return_value = False

        with patch.object(gui, "next") as mock_next:
            gui.onKeyDown(down_evt)
            mock_next.assert_called_once()

        # Test Up Arrow -> Previous Short
        up_evt = MagicMock()
        up_evt.ShiftDown.return_value = False
        up_evt.HasAnyModifiers.return_value = False
        up_evt.GetKeyCode.side_effect = lambda: wx.WXK_UP

        with patch.object(gui, "previous") as mock_prev:
            gui.onKeyDown(up_evt)
            mock_prev.assert_called_once()

        # Test Shift+Up Arrow -> Volume Up
        shift_up_evt = MagicMock()
        shift_up_evt.ShiftDown.return_value = True
        shift_up_evt.HasAnyModifiers.return_value = True
        shift_up_evt.GetKeyCode.side_effect = lambda: wx.WXK_UP

        with patch.object(gui, "increase_volume") as mock_vol_up:
            gui.onKeyDown(shift_up_evt)
            mock_vol_up.assert_called_once()

        # Test Shift+Down Arrow -> Volume Down
        shift_down_evt = MagicMock()
        shift_down_evt.ShiftDown.return_value = True
        shift_down_evt.HasAnyModifiers.return_value = True
        shift_down_evt.GetKeyCode.side_effect = lambda: wx.WXK_DOWN

        with patch.object(gui, "decrease_volume") as mock_vol_down:
            gui.onKeyDown(shift_down_evt)
            mock_vol_down.assert_called_once()

        gui.closeAction()


def test_media_gui_shorts_preloading():
    mock_stream1 = MagicMock(url="http://stream1")
    mock_stream2 = MagicMock(url="http://stream2")

    shorts_list = [
        {
            "id": "short1",
            "title": "Short 1",
            "url": "https://www.youtube.com/shorts/short1",
        },
        {
            "id": "short2",
            "title": "Short 2",
            "url": "https://www.youtube.com/shorts/short2",
        },
        {
            "id": "short3",
            "title": "Short 3",
            "url": "https://www.youtube.com/shorts/short3",
        },
    ]

    with (
        patch("media_player.media_gui.Player"),
        patch(
            "media_player.media_gui.utils.get_video_like_info",
            return_value={"likes": 5, "rating": None},
        ),
        patch(
            "media_player.media_gui.utils.get_playable_stream",
            return_value=mock_stream2,
        ),
    ):
        gui = MediaGui(
            parent=None,
            title="Short 1",
            stream=mock_stream1,
            url="https://www.youtube.com/shorts/short1",
            can_download=True,
            results=shorts_list,
            shorts_mode=True,
        )

        gui._preload_next_shorts()
        gui.preloaded_streams["https://www.youtube.com/shorts/short2"] = mock_stream2

        with patch.object(gui, "_perform_track_change"):
            gui.changeTrack(1)

        assert gui.current_index == 1
        gui.closeAction()


def test_media_gui_context_awareness():
    mock_stream = MagicMock(url="http://stream1")
    shorts_list = [
        {
            "id": "short1",
            "title": "Short 1",
            "url": "https://www.youtube.com/shorts/short1",
        },
        {
            "id": "short2",
            "title": "Short 2",
            "url": "https://www.youtube.com/shorts/short2",
        },
    ]

    with (
        patch("media_player.media_gui.Player"),
        patch(
            "media_player.media_gui.utils.get_video_like_info",
            return_value={"likes": 5, "rating": None},
        ),
    ):
        gui = MediaGui(
            parent=None,
            title="Short 1",
            stream=mock_stream,
            url="https://www.youtube.com/shorts/short1",
            can_download=True,
            results=shorts_list,
            shorts_mode=True,
        )

        assert gui.url == "https://www.youtube.com/shorts/short1"

        with (
            patch("media_player.media_gui.utils.copy_to_clipboard") as mock_copy,
            patch("wx.MessageBox"),
        ):
            gui.onCopy(None)
            mock_copy.assert_called_once_with("https://www.youtube.com/shorts/short1")

        with (
            patch(
                "media_player.media_gui.utils.like_video",
                return_value={"success": True},
            ) as mock_like,
            patch("media_player.media_gui.speak"),
        ):
            gui.onLike(None)
            import time

            time.sleep(0.1)
            mock_like.assert_called_once_with(
                "https://www.youtube.com/shorts/short1", "like", parent=gui
            )

        gui.closeAction()


def test_media_gui_shorts_title_update_and_cache_retention():
    mock_stream1 = MagicMock(url="http://stream1", title="Real Short 1 Title")
    mock_stream2 = MagicMock(url="http://stream2", title="Real Short 2 Title")

    shorts_list = [
        {
            "id": "short1",
            "title": "Short (short1)",
            "url": "https://www.youtube.com/shorts/short1",
        },
        {
            "id": "short2",
            "title": "Short (short2)",
            "url": "https://www.youtube.com/shorts/short2",
        },
    ]

    with (
        patch("media_player.media_gui.Player"),
        patch(
            "media_player.media_gui.utils.get_video_like_info",
            return_value={"likes": 5, "rating": None},
        ),
        patch("media_player.media_gui.speak"),
    ):
        gui = MediaGui(
            parent=None,
            title="Short (short1)",
            stream=mock_stream1,
            url="https://www.youtube.com/shorts/short1",
            can_download=True,
            results=shorts_list,
            shorts_mode=True,
        )

        gui.preloaded_streams["https://www.youtube.com/shorts/short1"] = mock_stream1
        gui.preloaded_streams["https://www.youtube.com/shorts/short2"] = mock_stream2

        # Cycle to index 1 (short2)
        gui.changeTrack(1)
        # Preloaded stream should be retained in dictionary (not popped)
        assert "https://www.youtube.com/shorts/short2" in gui.preloaded_streams
        assert gui.results[1]["title"] == "Real Short 2 Title"

        # Cycle back to index 0 (short1)
        gui.changeTrack(0)
        assert "https://www.youtube.com/shorts/short1" in gui.preloaded_streams
        assert gui.results[0]["title"] == "Real Short 1 Title"

        gui.closeAction()


def test_shorts_looping_options_and_reset():
    mock_stream = MagicMock(url="http://stream1", title="Short Video Title")
    mock_player_inst = MagicMock()

    with (
        patch("media_player.media_gui.Player", return_value=mock_player_inst),
        patch(
            "media_player.media_gui.utils.get_video_like_info",
            return_value={"likes": 5, "rating": None},
        ),
    ):
        gui = MediaGui(
            parent=None,
            title="Short Video Title",
            stream=mock_stream,
            url="https://www.youtube.com/shorts/short1",
            can_download=True,
            results=[
                {
                    "id": "short1",
                    "title": "Short Video Title",
                    "url": "https://www.youtube.com/shorts/short1",
                }
            ],
            shorts_mode=True,
        )

        gui._perform_track_change(
            mock_stream, "https://www.youtube.com/shorts/short1", "Short Video Title", 0
        )

        # Ensure loop-file=inf was passed in options to set_media
        mock_player_inst.set_media.assert_called()
        call_args = mock_player_inst.set_media.call_args
        options = call_args[1].get("options", [])
        assert "loop-file=inf" in options

        gui.closeAction()
