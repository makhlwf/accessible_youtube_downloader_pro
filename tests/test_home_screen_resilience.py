from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import accessible_youtube_downloader_pro as main


def test_home_feed_checks_dependencies_before_starting_worker(monkeypatch):
    home = MagicMock()
    home._home_feed_request = None
    home._shutting_down = Event()
    home.home_feed_continuation = "page-two"
    monkeypatch.setattr(main.settings_handler, "config_get", lambda key: "cookies.txt")
    deno_check = MagicMock(return_value=True)
    cookies_check = MagicMock(return_value=True)
    get_feed = MagicMock(return_value={"videos": [], "continuation": None})
    monkeypatch.setattr(main.utils, "ensure_deno_installed", deno_check)
    monkeypatch.setattr(main.utils, "ensure_cookies_configured", cookies_check)
    monkeypatch.setattr(main.utils, "get_home_feed", get_feed)
    worker = MagicMock()
    monkeypatch.setattr(main.threading, "Thread", worker)
    queue = MagicMock()
    monkeypatch.setattr(main, "wx", SimpleNamespace(CallAfter=queue))

    main.HomeScreen.load_home_feed(home, load_more=True)
    main.HomeScreen.load_home_feed(home, load_more=True)

    deno_check.assert_called_once()
    cookies_check.assert_called_once()
    worker.return_value.start.assert_called_once()
    get_feed.assert_not_called()
    worker.call_args.kwargs["target"]()
    get_feed.assert_called_once_with("page-two", cookies_path="cookies.txt")
    cookies_path, token = home._home_feed_request
    queue.assert_called_once_with(
        home._finish_home_feed, cookies_path, token, get_feed.return_value, True
    )


def test_home_feed_drops_stale_completion_after_account_change(monkeypatch):
    home = MagicMock()
    home._shutting_down = Event()
    token = object()
    home._home_feed_request = ("old-cookies.txt", token)
    monkeypatch.setattr(
        main.settings_handler, "config_get", lambda key: "new-cookies.txt"
    )

    main.HomeScreen._finish_home_feed(home, "old-cookies.txt", token, {}, False)

    assert home._home_feed_request is None
    home._update_home_feed.assert_not_called()


def test_home_feed_placeholder_does_not_dispatch_playback_or_prefetch():
    home = MagicMock()
    home.home_feed_data = []
    home.home_feed_list.GetSelection.return_value = 0
    home.home_feed_list.Selection = 0

    main.HomeScreen.on_home_feed_play(home, None)
    main.HomeScreen.on_home_feed_list_box(home, None)

    home.home_feed_results.get_stream.assert_not_called()
    home.scraper.add_item.assert_not_called()


def test_failed_mix_playback_leaves_home_visible(monkeypatch):
    from media_player import media_gui

    home = MagicMock()
    home.home_feed_data = [{"type": "mix", "playlistId": "RDmix", "id": "seed"}]
    home.home_feed_list.GetSelection.return_value = 0
    play_mix = MagicMock(return_value=None)
    monkeypatch.setattr(media_gui, "play_mix", play_mix)

    main.HomeScreen.on_home_feed_play(home, None)

    play_mix.assert_called_once_with(home, "RDmix", "seed", audio_mode=False)
    home.Hide.assert_not_called()


def test_ipc_listener_survives_connection_read_error(monkeypatch):
    home = MagicMock()
    home._shutting_down = Event()
    broken = MagicMock()
    broken.recv.side_effect = ConnectionResetError
    good = MagicMock()
    good.recv.side_effect = [b'{"action":"show"}', b""]
    sockets = MagicMock()
    server = sockets.return_value.__enter__.return_value

    def accept():
        if server.accept.call_count == 1:
            return broken, None
        if server.accept.call_count == 2:
            return good, None
        home._shutting_down.set()
        raise TimeoutError

    server.accept.side_effect = accept
    monkeypatch.setattr(main.socket, "socket", sockets)
    worker = MagicMock()
    monkeypatch.setattr(main.threading, "Thread", worker)
    queue = MagicMock()
    monkeypatch.setattr(main, "wx", SimpleNamespace(CallAfter=queue))

    main.HomeScreen._start_ipc_server(home)
    worker.call_args.kwargs["target"]()

    assert queue.call_args_list == [
        call(home._handle_ipc_message, b'{"action":"show"}')
    ]
    broken.__exit__.assert_called_once()
    good.__exit__.assert_called_once()


def test_ipc_handler_ignores_bad_input_and_callbacks_during_shutdown():
    home = MagicMock()
    home._shutting_down = Event()
    main.HomeScreen._handle_ipc_message(home, b"[]")
    main.HomeScreen._handle_ipc_message(home, b'{"action":"open_url","url":[]}')
    main.HomeScreen._handle_ipc_message(home, b"SHOW")
    home._shutting_down.set()
    main.HomeScreen._handle_ipc_message(home, b'{"action":"show"}')

    home.handle_external_url.assert_not_called()
    home.tray_icon.on_show.assert_called_once_with(None)
