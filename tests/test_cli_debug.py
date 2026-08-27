import logging
from unittest.mock import MagicMock, patch

import accessible_youtube_downloader_pro as app_main
from accessible_youtube_downloader_pro import get_launch_url, is_debug_invocation


def test_is_debug_invocation_flags():
    assert is_debug_invocation(["HexPlayer.exe", "-d"]) is True
    assert is_debug_invocation(["HexPlayer.exe", "--debug"]) is True
    assert (
        is_debug_invocation(
            ["accessible_youtube_downloader_pro.py", "-d", "https://youtu.be/123"]
        )
        is True
    )
    assert (
        is_debug_invocation(
            ["accessible_youtube_downloader_pro.py", "--debug", "https://youtu.be/123"]
        )
        is True
    )
    assert is_debug_invocation(["HexPlayer.exe"]) is False
    assert is_debug_invocation(["HexPlayer.exe", "--background"]) is False
    assert is_debug_invocation(["HexPlayer.exe", "https://youtu.be/123"]) is False


def test_get_launch_url_ignores_cli_flags():
    assert (
        get_launch_url(
            ["HexPlayer.exe", "-d", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        )
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert (
        get_launch_url(
            ["HexPlayer.exe", "--debug", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        )
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    assert get_launch_url(["HexPlayer.exe", "-d"]) == ""
    assert get_launch_url(["HexPlayer.exe", "--debug"]) == ""
    assert get_launch_url(["HexPlayer.exe", "--background"]) == ""
    assert (
        get_launch_url(["HexPlayer.exe", "https://youtu.be/dQw4w9WgXcQ"])
        == "https://youtu.be/dQw4w9WgXcQ"
    )


def test_enable_console_output_attaches_to_parent(monkeypatch):
    mock_kernel32 = MagicMock()
    mock_kernel32.AttachConsole.return_value = 1
    mock_kernel32.AllocConsole.return_value = 1

    monkeypatch.setattr(app_main.sys, "platform", "win32")
    with (
        patch("ctypes.windll.kernel32", mock_kernel32, create=True),
        patch("builtins.open", MagicMock()),
    ):
        result = app_main.enable_console_output()
        assert result is True
        mock_kernel32.AttachConsole.assert_called_once_with(-1)
        mock_kernel32.AllocConsole.assert_not_called()


def test_enable_console_output_allocates_when_attach_fails(monkeypatch):
    mock_kernel32 = MagicMock()
    mock_kernel32.AttachConsole.return_value = 0
    mock_kernel32.AllocConsole.return_value = 1

    monkeypatch.setattr(app_main.sys, "platform", "win32")
    with (
        patch("ctypes.windll.kernel32", mock_kernel32, create=True),
        patch("builtins.open", MagicMock()),
    ):
        result = app_main.enable_console_output()
        assert result is True
        mock_kernel32.AttachConsole.assert_called_once_with(-1)
        mock_kernel32.AllocConsole.assert_called_once()


def test_setup_logging_with_cli_debug_flag(monkeypatch):
    root_logger = logging.getLogger()
    called_enable_console = []
    debug_messages = []

    monkeypatch.setattr(
        app_main, "enable_console_output", lambda: called_enable_console.append(True)
    )
    monkeypatch.setattr("settings_handler.config_get", lambda key: False)
    monkeypatch.setattr(
        root_logger, "debug", lambda msg, *args: debug_messages.append(msg)
    )

    app_main.setup_logging(["HexPlayer.exe", "-d"])
    assert root_logger.level == logging.DEBUG
    assert len(called_enable_console) == 1
    assert "Debug logging initialized (terminal output enabled)" in debug_messages


def test_setup_logging_with_config_debug_only(monkeypatch):
    root_logger = logging.getLogger()
    called_enable_console = []
    debug_messages = []

    monkeypatch.setattr(
        app_main, "enable_console_output", lambda: called_enable_console.append(True)
    )
    monkeypatch.setattr("settings_handler.config_get", lambda key: True)
    monkeypatch.setattr(
        root_logger, "debug", lambda msg, *args: debug_messages.append(msg)
    )

    app_main.setup_logging(["HexPlayer.exe"])
    assert root_logger.level == logging.DEBUG
    assert len(called_enable_console) == 0
    assert "Debug logging initialized" in debug_messages
    assert "Debug logging initialized (terminal output enabled)" not in debug_messages


def test_setup_logging_without_debug(monkeypatch):
    root_logger = logging.getLogger()
    called_enable_console = []

    monkeypatch.setattr(
        app_main, "enable_console_output", lambda: called_enable_console.append(True)
    )
    monkeypatch.setattr("settings_handler.config_get", lambda key: False)

    app_main.setup_logging(["HexPlayer.exe"])
    assert root_logger.level == logging.INFO
    assert len(called_enable_console) == 0
