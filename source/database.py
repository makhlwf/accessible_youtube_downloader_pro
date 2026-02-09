import sqlite3 as sql
import logging
from paths import db_path

logger = logging.getLogger(__name__)


def db_init():
    try:
        connection = sql.connect(db_path, check_same_thread=False)
        connection.row_factory = sql.Row
        return connection
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return None


def is_valid(function):
    def wrapper(*args, **kwargs):
        if con is not None:
            try:
                return function(*args, **kwargs)
            except sql.Error as e:
                logger.error(f"Database error in {function.__name__}: {e}")
        return None

    return wrapper


@is_valid
def prepare_tables():
    favorites_query = """
    CREATE TABLE IF NOT EXISTS favorite (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        display_title TEXT NOT NULL,
        url TEXT NOT NULL,
        is_live INTEGER NOT NULL,
        channel_name TEXT NOT NULL,
        channel_url TEXT NOT NULL
    )"""
    con.execute(favorites_query)
    continue_query = """
    CREATE TABLE IF NOT EXISTS continue (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL,
        position REAL NOT NULL
    )"""
    con.execute(continue_query)
    con.commit()


@is_valid
def disconnect():
    con.close()


class Favorite:
    @is_valid
    def add_favorite(self, data):
        query = """
        INSERT INTO favorite (title, display_title, url, is_live, channel_name, channel_url)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        con.execute(
            query,
            (
                data["title"],
                data["display_title"],
                data["url"],
                data["live"],
                data["channel_name"],
                data["channel_url"],
            ),
        )
        con.commit()

    @is_valid
    def remove_favorite(self, url):
        con.execute("DELETE FROM favorite WHERE url = ?", (url,))
        con.commit()

    @is_valid
    def get_all(self):
        cursor = con.execute(
            "SELECT title, display_title, url, is_live, channel_name, channel_url FROM favorite"
        )
        rows = cursor.fetchall()
        data = []
        for row in rows:
            data.append(
                {
                    "title": row["title"],
                    "display_title": row["display_title"],
                    "url": row["url"],
                    "live": row["is_live"],
                    "channel_name": row["channel_name"],
                    "channel_url": row["channel_url"],
                }
            )
        return data


class Continue:
    @classmethod
    @is_valid
    def new_continue(cls, url, position):
        query = "INSERT INTO continue (url, position) VALUES (?, ?)"
        con.execute(query, (url, position))
        con.commit()

    @classmethod
    @is_valid
    def get_all(cls):
        cursor = con.execute("SELECT url, position FROM continue")
        rows = cursor.fetchall()
        data = {}
        for row in rows:
            data[row["url"]] = row["position"]
        return data

    @classmethod
    @is_valid
    def update(cls, url, position):
        query = "UPDATE continue SET position = ? WHERE url = ?"
        con.execute(query, (position, url))
        con.commit()

    @classmethod
    @is_valid
    def remove_continue(cls, url):
        con.execute("DELETE FROM continue WHERE url = ?", (url,))
        con.commit()


con = db_init()
prepare_tables()
