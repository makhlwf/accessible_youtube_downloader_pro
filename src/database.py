import logging
import sqlite3 as sql
import threading
import time

from paths import db_path

logger = logging.getLogger(__name__)
_db_lock = threading.RLock()


def db_init():
    try:
        connection = sql.connect(db_path, check_same_thread=False)
        connection.row_factory = sql.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        return connection
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return None


def is_valid(function):
    def wrapper(*args, **kwargs):
        if con is not None:
            with _db_lock:
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
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_favorite_url
        ON favorite (url)
        """
    )
    continue_query = """
    CREATE TABLE IF NOT EXISTS continue (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL,
        position REAL NOT NULL
    )"""
    con.execute(continue_query)
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_continue_url
        ON continue (url)
        """
    )
    history_query = """
    CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        display_title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        is_live INTEGER NOT NULL,
        channel_name TEXT NOT NULL,
        channel_url TEXT NOT NULL,
        watched_seconds REAL NOT NULL DEFAULT 0,
        last_played REAL NOT NULL
    )"""
    con.execute(history_query)
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_watch_history_last_played
        ON watch_history (last_played DESC)
        """
    )
    con.commit()


def disconnect():
    global con
    with _db_lock:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
            con = None


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
    def is_favorite(self, url):
        cursor = con.execute("SELECT 1 FROM favorite WHERE url = ? LIMIT 1", (url,))
        return cursor.fetchone() is not None

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


class WatchHistory:
    @classmethod
    @is_valid
    def add_or_update(cls, data):
        url = data.get("url", "")
        if not url:
            return

        title = data.get("title") or data.get("display_title") or url
        channel_name = data.get("channel_name") or data.get("author") or ""
        channel_url = data.get("channel_url") or ""
        display_title = data.get("display_title") or (
            f"{title}. {channel_name}" if channel_name else title
        )
        watched_seconds = data.get("watched_seconds") or 0
        try:
            watched_seconds = max(0, float(watched_seconds))
        except TypeError, ValueError:
            watched_seconds = 0

        query = """
        INSERT INTO watch_history (
            title, display_title, url, is_live, channel_name, channel_url,
            watched_seconds, last_played
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title = CASE
                WHEN excluded.title != '' THEN excluded.title
                ELSE watch_history.title
            END,
            display_title = CASE
                WHEN excluded.display_title != '' THEN excluded.display_title
                ELSE watch_history.display_title
            END,
            is_live = excluded.is_live,
            channel_name = CASE
                WHEN excluded.channel_name != '' THEN excluded.channel_name
                ELSE watch_history.channel_name
            END,
            channel_url = CASE
                WHEN excluded.channel_url != '' THEN excluded.channel_url
                ELSE watch_history.channel_url
            END,
            watched_seconds = CASE
                WHEN excluded.watched_seconds > 0 THEN excluded.watched_seconds
                ELSE watch_history.watched_seconds
            END,
            last_played = excluded.last_played
        """
        con.execute(
            query,
            (
                title,
                display_title,
                url,
                1 if data.get("is_live") or data.get("live") else 0,
                channel_name,
                channel_url,
                watched_seconds,
                time.time(),
            ),
        )
        con.commit()

    @classmethod
    @is_valid
    def get_page(cls, limit=50, offset=0):
        cursor = con.execute(
            """
            SELECT
                title, display_title, url, is_live, channel_name, channel_url,
                watched_seconds, last_played
            FROM watch_history
            ORDER BY last_played DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        data = []
        for row in rows:
            channel_name = row["channel_name"]
            data.append(
                {
                    "title": row["title"],
                    "display_title": row["display_title"],
                    "url": row["url"],
                    "is_live": row["is_live"],
                    "live": row["is_live"],
                    "channel_name": channel_name,
                    "channel_url": row["channel_url"],
                    "author": channel_name,
                    "watched_seconds": row["watched_seconds"],
                    "last_played": row["last_played"],
                    "type": "video",
                }
            )
        return data

    @classmethod
    @is_valid
    def clear(cls):
        con.execute("DELETE FROM watch_history")
        con.commit()


con = db_init()
prepare_tables()
