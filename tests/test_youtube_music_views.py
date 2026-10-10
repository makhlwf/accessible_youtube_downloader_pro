"""Tests for youtube_music.views fetch closures (service patched, no network)."""

from unittest.mock import MagicMock, patch

from youtube_music import views


def _patch_service(service):
    return patch("youtube_music.views.get_service", return_value=service)


def test_home_view_flattens_sections():
    service = MagicMock()
    service.get_home.return_value = [
        {"title": "Quick picks", "contents": [{"videoId": "v1", "title": "A"}]},
        {"title": "Listen again", "contents": [{"videoId": "v2", "title": "B"}]},
        "garbage",  # non-dict section must be ignored
    ]
    with _patch_service(service):
        view = views.HomeView(MagicMock(scraper=None))
        rows = view.fetch()
    assert [r["videoId"] for r in rows] == ["v1", "v2"]


def test_home_view_empty():
    service = MagicMock()
    service.get_home.return_value = []
    with _patch_service(service):
        assert views.HomeView(MagicMock(scraper=None)).fetch() == []


def test_album_view_resolves_browse_id_when_missing():
    service = MagicMock()
    service.get_album_browse_id.return_value = "MPREreal"
    service.get_album.return_value = {"tracks": [{"videoId": "v1", "title": "T"}]}
    row = {"title": "Album", "playlistId": "OLAK5uy", "browseId": None}
    with _patch_service(service):
        view = views.album_view(MagicMock(scraper=None), row)
        rows = view.fetch()
    service.get_album_browse_id.assert_called_once_with("OLAK5uy")
    assert rows[0]["videoId"] == "v1"


def test_playlist_view_normalizes_tracks():
    service = MagicMock()
    service.get_playlist.return_value = {
        "tracks": [{"videoId": "v", "title": "t", "setVideoId": "s"}]
    }
    row = {"title": "PL", "playlistId": "PL123"}
    with _patch_service(service):
        rows = views.playlist_view(MagicMock(scraper=None), row).fetch()
    assert rows[0]["setVideoId"] == "s"


def test_artist_view_collects_sections():
    service = MagicMock()
    service.get_artist.return_value = {
        "songs": {"results": [{"videoId": "v1", "title": "s1"}]},
        "albums": {"results": [{"browseId": "MPREa", "title": "al"}]},
        "unrelated": "ignored",
    }
    row = {"title": "Artist", "browseId": "UCchan"}
    with _patch_service(service):
        rows = views.artist_view(MagicMock(scraper=None), row).fetch()
    assert len(rows) == 2


def test_search_view_normalizes_results():
    service = MagicMock()
    service.search.return_value = [
        {"videoId": "v", "title": "res", "resultType": "song"}
    ]
    with _patch_service(service):
        rows = views.search_view(MagicMock(scraper=None), "query").fetch()
    assert rows[0]["type"] == "song"
    service.search.assert_called_once()


def test_library_liked_reads_tracks_key():
    service = MagicMock()
    service.get_liked_songs.return_value = {
        "tracks": [{"videoId": "v", "title": "liked"}]
    }
    with _patch_service(service):
        rows = views.library_view(MagicMock(scraper=None), "liked").fetch()
    assert rows[0]["title"] == "liked"


def test_library_history_reads_list():
    service = MagicMock()
    service.get_history.return_value = [{"videoId": "v", "title": "watched"}]
    with _patch_service(service):
        rows = views.library_view(MagicMock(scraper=None), "history").fetch()
    assert rows[0]["title"] == "watched"


def test_moods_view_extracts_params_rows():
    service = MagicMock()
    service.get_mood_categories.return_value = {
        "Moods & moments": [{"title": "Chill", "params": "ggMP"}],
        "Genres": [{"title": "Pop"}],  # no params -> skipped
    }
    with _patch_service(service):
        rows = views.moods_view(MagicMock(scraper=None)).fetch()
    assert len(rows) == 1
    assert rows[0]["type"] == "mood"
    assert rows[0]["params"] == "ggMP"
