from unittest.mock import patch

import utils
from accessible_youtube_downloader_pro import HomeScreen


def test_get_subscribed_channels_success(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("cookie_data")
    mock_response = {
        "channels": [
            {
                "id": "UCchannel1",
                "name": "Channel One",
                "subscribers": "1.2M subscribers",
                "url": "https://www.youtube.com/channel/UCchannel1",
            },
            {
                "id": "UCchannel2",
                "name": "Channel Two",
                "subscribers": "34K subscribers",
                "url": "https://www.youtube.com/channel/UCchannel2",
            },
        ]
    }
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
        patch("utils.config_get", return_value=str(cookie_file)),
        patch("utils.deno_service.send_command", return_value=mock_response),
    ):
        result = utils.get_subscribed_channels()
        assert "error" not in result
        assert len(result["channels"]) == 2
        assert result["channels"][0]["name"] == "Channel One"
        assert result["channels"][0]["subscribers"] == "1.2M subscribers"
        assert (
            result["channels"][1]["url"] == "https://www.youtube.com/channel/UCchannel2"
        )


def test_get_subscribed_channels_service_error(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("cookie_data")
    with (
        patch("utils.ensure_deno_installed", return_value=True),
        patch("utils.ensure_cookies_configured", return_value=True),
        patch("utils.config_get", return_value=str(cookie_file)),
        patch(
            "utils.deno_service.send_command",
            return_value={"error": "Not logged in with provided cookies"},
        ),
    ):
        result = utils.get_subscribed_channels()
        assert result["channels"] == []
        assert result["error"] == "Not logged in with provided cookies"


def test_get_subscribed_channels_no_cookies():
    with patch("utils.ensure_cookies_configured", return_value=False):
        result = utils.get_subscribed_channels()
        assert result["channels"] == []
        assert "error" not in result


def test_home_screen_subscriptions_button_visibility(tmp_path):
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
        assert home.subscriptionsBtn.IsShown() is True
        home.subscriptionsItem.Enable.assert_called_with(True)

        with patch(
            "accessible_youtube_downloader_pro.utils.has_cookies_file",
            return_value=False,
        ):
            home.update_shorts_button_visibility()
            assert home.subscriptionsBtn.IsShown() is False
            home.subscriptionsItem.Enable.assert_called_with(False)


def test_subscriptions_dialog_update_channels_success():
    from unittest.mock import MagicMock

    parent_mock = MagicMock()
    with patch("gui.subscriptions_dialog.SubscriptionsDialog.load_channels"):
        from gui.subscriptions_dialog import SubscriptionsDialog

        dlg = SubscriptionsDialog(parent_mock)
        data = {
            "channels": [
                {
                    "name": "Tech Channel",
                    "subscribers": "100K subscribers",
                    "url": "https://www.youtube.com/@tech",
                }
            ]
        }
        with patch("gui.subscriptions_dialog.speak") as mock_speak:
            dlg._update_channels(data)
            assert len(dlg.channels) == 1
            assert dlg.channelsList.Items == ["Tech Channel, 100K subscribers"]
            assert dlg.channelsList.GetSelection() == 0
            mock_speak.assert_called()


def test_subscriptions_dialog_update_channels_error():
    from unittest.mock import MagicMock

    parent_mock = MagicMock()
    with patch("gui.subscriptions_dialog.SubscriptionsDialog.load_channels"):
        from gui.subscriptions_dialog import SubscriptionsDialog

        dlg = SubscriptionsDialog(parent_mock)
        with (
            patch("gui.subscriptions_dialog.wx.MessageBox") as mock_box,
            patch("gui.subscriptions_dialog.speak") as mock_speak,
        ):
            dlg._update_channels({"error": "Failed to fetch"})
            mock_box.assert_called_once()
            mock_speak.assert_called_with("Failed to fetch")


def test_subscriptions_dialog_open_channel():
    from unittest.mock import MagicMock

    parent_mock = MagicMock()
    with patch("gui.subscriptions_dialog.SubscriptionsDialog.load_channels"):
        from gui.subscriptions_dialog import SubscriptionsDialog

        dlg = SubscriptionsDialog(parent_mock)
        dlg.channels = [{"name": "Tech", "url": "https://www.youtube.com/@tech"}]
        dlg.channelsList.GetSelection = MagicMock(return_value=0)
        with patch("gui.subscriptions_dialog.ChannelDialog") as mock_cd:
            dlg.open_channel()
            mock_cd.assert_called_once_with(
                dlg, "https://www.youtube.com/@tech", "Tech"
            )
