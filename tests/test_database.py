import sqlite3
from unittest.mock import patch

import pytest

import database


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with patch("database.con", conn):
        database.prepare_tables()
        yield conn
    conn.close()


def test_favorite_operations(test_db):
    fav = database.Favorite()
    data = {
        "title": "Test Title",
        "display_title": "Test Display Title",
        "url": "https://youtube.com/watch?v=123",
        "live": 0,
        "channel_name": "Test Channel",
        "channel_url": "https://youtube.com/channel/123",
    }

    with patch("database.con", test_db):
        fav.add_favorite(data)
        favorites = fav.get_all()
        assert len(favorites) == 1
        assert favorites[0]["title"] == "Test Title"
        assert favorites[0]["url"] == "https://youtube.com/watch?v=123"

        fav.remove_favorite(data["url"])
        favorites = fav.get_all()
        assert len(favorites) == 0
        assert fav.is_favorite(data["url"]) is False

        fav.add_favorite(data)
        assert fav.is_favorite(data["url"]) is True
        assert fav.is_favorite("https://youtube.com/watch?v=nonexistent") is False


def test_continue_operations(test_db):
    cont = database.Continue()
    url = "https://youtube.com/watch?v=456"
    position = 10.5

    with patch("database.con", test_db):
        cont.new_continue(url, position)
        all_continues = cont.get_all()
        assert all_continues[url] == position

        new_position = 20.0
        cont.update(url, new_position)
        all_continues = cont.get_all()
        assert all_continues[url] == new_position

        cont.remove_continue(url)
        all_continues = cont.get_all()
        assert url not in all_continues


def test_watch_history_add_update_and_page(test_db):
    history = database.WatchHistory()
    url = "https://youtube.com/watch?v=789"

    with patch("database.con", test_db):
        history.add_or_update(
            {
                "title": "First Title",
                "url": url,
                "channel_name": "First Channel",
                "channel_url": "https://youtube.com/channel/789",
                "watched_seconds": 10,
            }
        )
        history.add_or_update(
            {
                "title": "Updated Title",
                "url": url,
                "channel_name": "",
                "watched_seconds": 0,
            }
        )

        page = history.get_page(limit=10, offset=0)
        assert len(page) == 1
        assert page[0]["title"] == "Updated Title"
        assert page[0]["author"] == "First Channel"
        assert page[0]["watched_seconds"] == 10
        assert page[0]["url"] == url


def test_search_history_persistence_and_unicode(tmp_path):
    path = tmp_path / "history.db"
    for attempt in range(2):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            with patch("database.con", conn):
                database.prepare_tables()
                if attempt == 0:
                    database.SearchHistory.add("موسيقى")
                    database.SearchHistory.add("Straße")
                    database.SearchHistory.add("STRASSE")
                    database.SearchHistory.add("it's a query")
                assert database.SearchHistory.get_recent() == [
                    "it's a query",
                    "STRASSE",
                    "موسيقى",
                ]
        finally:
            conn.close()


def test_search_history_clear(test_db):
    database.SearchHistory.add("query")
    assert database.SearchHistory.clear() is True
    assert database.SearchHistory.get_recent() == []


def test_search_history_unavailable():
    with patch("database.con", None):
        assert database.SearchHistory.get_recent() is None
        assert database.SearchHistory.add("query") is None
        assert database.SearchHistory.clear() is None


def test_search_history_add(test_db):
    assert database.SearchHistory.add("  cats  ") is True
    database.SearchHistory.add("dogs")
    database.SearchHistory.add("CATS")
    assert database.SearchHistory.get_recent() == ["CATS", "dogs"]
    assert database.SearchHistory.add(" \t\n") is False
    assert database.SearchHistory.get_recent() == ["CATS", "dogs"]


def test_search_history_limit_and_recency(test_db):
    for index in range(55):
        assert database.SearchHistory.add(f"query {index}") is True
    assert database.SearchHistory.get_recent() == [
        f"query {index}" for index in range(54, 4, -1)
    ]
    database.SearchHistory.add("query 5")
    assert database.SearchHistory.get_recent() == ["query 5"] + [
        f"query {index}" for index in range(54, 5, -1)
    ]
