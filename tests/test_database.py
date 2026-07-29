import sqlite3
from unittest.mock import patch

import pytest

import database


@pytest.fixture
def test_db():
    # Setup an in-memory database for testing
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Replace the connection in the database module
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
