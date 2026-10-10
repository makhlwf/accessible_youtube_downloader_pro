"""Tests for youtube_music.service.YTMusicService.

Covers client selection (anon / auth / prefer_auth), AuthRequiredError when
signed out, guard error mapping (auth vs generic), reload_auth, the deferred
wrappers, and the process-wide singleton. ytmusicapi.YTMusic is patched so no
network or real client is ever constructed.
"""

from unittest.mock import MagicMock, patch

import pytest

from youtube_music import service as service_module
from youtube_music.errors import AuthRequiredError, YTMusicUnavailableError


def _make_service(headers=None, cookies_path="/fake/cookies.txt"):
    """Build a service with YTMusic patched and auth headers controlled."""
    svc = service_module.YTMusicService(cookies_path=cookies_path)
    return svc


@patch("youtube_music.service.YTMusic")
def test_anon_client_used_for_search(mock_ytmusic):
    client = MagicMock()
    client.search.return_value = [{"title": "x"}]
    mock_ytmusic.return_value = client
    svc = _make_service()
    with patch(
        "youtube_music.service.auth_bridge.build_browser_headers", return_value=None
    ):
        result = svc.search("hello")
    assert result == [{"title": "x"}]
    # anon client constructed with auth=None
    assert mock_ytmusic.call_args.kwargs.get("auth") is None
    client.search.assert_called_once()


@patch("youtube_music.service.YTMusic")
def test_auth_required_when_signed_out(mock_ytmusic):
    mock_ytmusic.return_value = MagicMock()
    svc = _make_service()
    with (
        patch(
            "youtube_music.service.auth_bridge.build_browser_headers", return_value=None
        ),
        pytest.raises(AuthRequiredError),
    ):
        svc.get_home()


@patch("youtube_music.service.YTMusic")
def test_auth_method_runs_when_cookies_present(mock_ytmusic):
    client = MagicMock()
    client.get_home.return_value = [{"title": "feed"}]
    mock_ytmusic.return_value = client
    svc = _make_service()
    headers = {"Cookie": "SAPISID=abc"}
    with patch(
        "youtube_music.service.auth_bridge.build_browser_headers", return_value=headers
    ):
        result = svc.get_home()
    assert result == [{"title": "feed"}]
    # auth client constructed with the headers dict
    assert any(
        call.kwargs.get("auth") == headers for call in mock_ytmusic.call_args_list
    )


@patch("youtube_music.service.YTMusic")
def test_guard_maps_403_to_auth_required(mock_ytmusic):
    client = MagicMock()
    client.get_home.side_effect = Exception("HTTP 403 Forbidden")
    mock_ytmusic.return_value = client
    svc = _make_service()
    with (
        patch(
            "youtube_music.service.auth_bridge.build_browser_headers",
            return_value={"Cookie": "x"},
        ),
        pytest.raises(AuthRequiredError),
    ):
        svc.get_home()


@patch("youtube_music.service.YTMusic")
def test_guard_maps_generic_to_unavailable(mock_ytmusic):
    client = MagicMock()
    client.search.side_effect = Exception("connection reset")
    mock_ytmusic.return_value = client
    svc = _make_service()
    with (
        patch(
            "youtube_music.service.auth_bridge.build_browser_headers", return_value=None
        ),
        pytest.raises(YTMusicUnavailableError),
    ):
        svc.search("q")


@patch("youtube_music.service.YTMusic")
def test_prefer_auth_uses_auth_client_when_available(mock_ytmusic):
    anon = MagicMock(name="anon")
    auth = MagicMock(name="auth")
    auth.get_playlist.return_value = {"title": "mine"}
    # First construction = anon (auth=None), second = auth (auth=headers)
    mock_ytmusic.side_effect = lambda **kw: auth if kw.get("auth") else anon
    svc = _make_service()
    with patch(
        "youtube_music.service.auth_bridge.build_browser_headers",
        return_value={"Cookie": "x"},
    ):
        result = svc.get_playlist("PL123")
    assert result == {"title": "mine"}
    auth.get_playlist.assert_called_once_with(
        "PL123", limit=100, related=False, suggestions_limit=0
    )


@patch("youtube_music.service.YTMusic")
def test_reload_auth_rebuilds_auth_client(mock_ytmusic):
    mock_ytmusic.return_value = MagicMock()
    svc = _make_service()
    with patch(
        "youtube_music.service.auth_bridge.build_browser_headers",
        return_value={"Cookie": "x"},
    ):
        svc.get_history()
        assert svc._auth is not None
        svc.reload_auth(cookies_path="/new/path.txt")
        assert svc._auth is None
        assert svc._cookies_path == "/new/path.txt"


@patch("youtube_music.service.YTMusic")
def test_rate_song_passes_rating(mock_ytmusic):
    client = MagicMock()
    mock_ytmusic.return_value = client
    svc = _make_service()
    with patch(
        "youtube_music.service.auth_bridge.build_browser_headers",
        return_value={"Cookie": "x"},
    ):
        svc.rate_song("vid123", "LIKE")
    args = client.rate_song.call_args.args
    assert args[0] == "vid123"
    # rating resolves to the enum member or the raw string under the mock
    assert str(args[1]).endswith("LIKE") or args[1] == "LIKE"


@patch("youtube_music.service.YTMusic")
def test_deferred_upload_wrapper_requires_auth(mock_ytmusic):
    mock_ytmusic.return_value = MagicMock()
    svc = _make_service()
    with (
        patch(
            "youtube_music.service.auth_bridge.build_browser_headers", return_value=None
        ),
        pytest.raises(AuthRequiredError),
    ):
        svc.get_library_upload_songs()


def test_get_service_singleton():
    with (
        patch("youtube_music.service._resolve_cookies_path", return_value=""),
        patch("youtube_music.service._resolve_language", return_value="en"),
    ):
        service_module._service_instance = None
        first = service_module.get_service()
        second = service_module.get_service()
        assert first is second
        third = service_module.get_service(refresh=True)
        assert third is not first
    service_module._service_instance = None
