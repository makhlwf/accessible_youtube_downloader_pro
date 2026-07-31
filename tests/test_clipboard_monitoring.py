from unittest.mock import MagicMock, patch

import utils


def test_copy_to_clipboard():
    mock_app = MagicMock()
    mock_top_win = MagicMock()
    mock_top_win.last_clip_content = ""
    mock_app.GetTopWindow.return_value = mock_top_win

    with (
        patch("wx.GetApp", return_value=mock_app),
        patch("pyperclip.copy") as mock_copy,
    ):
        utils.copy_to_clipboard("https://www.youtube.com/watch?v=test1234567")
        mock_copy.assert_called_once_with("https://www.youtube.com/watch?v=test1234567")
        assert (
            mock_top_win.last_clip_content
            == "https://www.youtube.com/watch?v=test1234567"
        )


def test_is_app_active():
    from accessible_youtube_downloader_pro import HomeScreen

    home_screen = MagicMock(spec=HomeScreen)
    home_screen.is_app_active = HomeScreen.is_app_active.__get__(
        home_screen, HomeScreen
    )

    mock_win = MagicMock()
    mock_win.IsShown.return_value = True
    mock_win.IsActive.return_value = True

    with (
        patch("wx.GetActiveWindow", return_value=None),
        patch("wx.GetTopLevelWindows", return_value=[mock_win]),
    ):
        assert home_screen.is_app_active() is True

    with (
        patch("wx.GetActiveWindow", return_value=None),
        patch("wx.GetTopLevelWindows", return_value=[]),
    ):
        assert home_screen.is_app_active() is False


def test_on_clip_timer_skips_when_app_active():
    from accessible_youtube_downloader_pro import HomeScreen

    home_screen = MagicMock(spec=HomeScreen)
    home_screen.last_clip_content = ""
    home_screen.is_app_active.return_value = True
    home_screen.on_clip_timer = HomeScreen.on_clip_timer.__get__(
        home_screen, HomeScreen
    )

    with (
        patch(
            "pyperclip.paste",
            return_value="https://www.youtube.com/watch?v=test1234567",
        ),
        patch("accessible_youtube_downloader_pro.AutoDetectDialog") as mock_dialog,
    ):
        home_screen.on_clip_timer(None)
        assert (
            home_screen.last_clip_content
            == "https://www.youtube.com/watch?v=test1234567"
        )
        mock_dialog.assert_not_called()


def test_on_clip_timer_skips_when_same_content():
    from accessible_youtube_downloader_pro import HomeScreen

    home_screen = MagicMock(spec=HomeScreen)
    home_screen.last_clip_content = "https://www.youtube.com/watch?v=test1234567"
    home_screen.is_app_active.return_value = False
    home_screen.on_clip_timer = HomeScreen.on_clip_timer.__get__(
        home_screen, HomeScreen
    )

    with (
        patch(
            "pyperclip.paste",
            return_value="https://www.youtube.com/watch?v=test1234567",
        ),
        patch("accessible_youtube_downloader_pro.AutoDetectDialog") as mock_dialog,
    ):
        home_screen.on_clip_timer(None)
        mock_dialog.assert_not_called()


def test_detect_from_clipboard_updates_last_clip_content():
    from accessible_youtube_downloader_pro import HomeScreen

    home_screen = MagicMock(spec=HomeScreen)
    home_screen.last_clip_content = ""
    home_screen.detectFromClipboard = HomeScreen.detectFromClipboard.__get__(
        home_screen, HomeScreen
    )

    with (
        patch(
            "pyperclip.paste",
            return_value="https://www.youtube.com/watch?v=test1234567",
        ),
        patch("accessible_youtube_downloader_pro.AutoDetectDialog") as mock_dialog,
    ):
        mock_dlg_instance = MagicMock()
        mock_dialog.return_value = mock_dlg_instance
        home_screen.detectFromClipboard(True)
        assert (
            home_screen.last_clip_content
            == "https://www.youtube.com/watch?v=test1234567"
        )
        mock_dialog.assert_called_once_with(
            home_screen, "https://www.youtube.com/watch?v=test1234567"
        )
