---
name: sqlite-state-storage
description: >-
  Use when creating, modifying, or querying database tables,
  managing favorites, watch history, resume positions, or updating application configuration settings.
---

# SQLite State Storage & Settings Management

## Overview

HexPlayer maintains user state (favorites, resume positions, watch history) in a local SQLite database (`%APPDATA%\HexPlayer\aHexPlayer.db`) managed by `src/database.py`. It also persists user preferences in `settings.ini` via `src/settings_handler.py`. Because background threads simultaneously read and update playback state, all database and configuration access is thread-safe and debounced.

## When to Use

- Adding or modifying tables, columns, or queries in `src/database.py`.
- Working with user favorites, playback bookmarks (`continue` table), or watch history.
- Adding new configuration keys in `src/settings_handler.py` or `settings.ini`.
- Handling multi-threaded database locking (`sqlite3.OperationalError: database is locked`).
- Managing portable mode vs standard Windows `%APPDATA%` directory storage in `paths.py`.

**When NOT to use:**
- Handling remote YouTube data fetching (use `innertube-rpc-bridge`).

## Core Patterns & Invariants

### 1. Thread-Safe Connection Wrapper via `RLock`
Python's standard `sqlite3.connect` is not safe for concurrent multi-threaded writes. All queries must be executed through the thread-safe connection wrapper:

```python
# ✅ REQUIRED: All DB operations must be serialized via threading.RLock
import threading
import sqlite3


class ThreadSafeDatabase:
    def __init__(self, db_path):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)

    def execute(self, query, params=()):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            self._conn.commit()
            return cursor
```

### 2. Atomic UPSERT Semantics
Updating seek positions or watch history must use idempotent SQLite `INSERT ... ON CONFLICT(url) DO UPDATE` to prevent race conditions:

```sql
-- Atomic resume seek position update
INSERT INTO continue (url, position)
VALUES (?, ?)
ON CONFLICT(url) DO UPDATE SET position = excluded.position;
```

### 3. Idempotent Schema Migrations
Never drop existing user data when modifying schemas. Use `CREATE TABLE IF NOT EXISTS` and check for missing columns before executing `ALTER TABLE`:

```python
def init_db(self):
    with self._lock:
        self.execute("""
            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                display_title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                is_live INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                channel_url TEXT NOT NULL,
                watched_seconds REAL NOT NULL DEFAULT 0,
                last_played REAL NOT NULL
            );
        """)
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_watch_history_last_played ON watch_history(last_played DESC);"
        )
```

### 4. Debounced Settings Persistence
Settings changes triggered rapidly by the UI (e.g. volume or equalizer sliders) must be debounced or written to memory first, flushing to disk asynchronously to prevent I/O micro-stutters:

```python
# Debounced save in settings_handler.py
def config_set(key, value):
    _config_cache[key] = value
    _schedule_debounced_disk_flush()
```

## Quick Reference

| Table Name | Primary Keys / Indexes | Purpose |
| :--- | :--- | :--- |
| `favorite` | `id PK`, `url` | Stored favorite videos, channels, playlists |
| `continue` | `id PK`, `url UNIQUE` | Last watched playback timestamp |
| `watch_history` | `id PK`, `url UNIQUE`, `last_played INDEX` | History log with duration and timestamps |

## Implementation Procedures

### Step 1: Adding a New Field to Favorites
1. Check if column exists via `PRAGMA table_info(favorite)`.
2. If missing, execute `ALTER TABLE favorite ADD COLUMN new_field TEXT DEFAULT ''`.
3. Update insert and fetch helper methods in `src/database.py`.
4. Add unit test in `tests/test_database.py`.

### Step 2: Adding a New Configuration Setting
1. Add default fallback value in `src/settings_handler.py` defaults dict.
2. Read with `config_get("new_setting", default="fallback")`.
3. Save with `config_set("new_setting", "value")`.

## Common Mistakes & Anti-Patterns

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| Opening raw `sqlite3.connect` per query | Disk contention, locked database errors | Use shared connection with `RLock` |
| Direct synchronous disk writes on slider move | Disk thrashing, audio stutter during drag | Debounce file writes |
| Missing `ON CONFLICT` in history | Duplicate URL throws UNIQUE constraint error | Use atomic UPSERT query |
| Hardcoding `C:\Users\...` paths | Breaks portability and other user accounts | Use `paths.py` resolvers |

## Verification & Quality Gates

- **Unit Tests**: Run `uv run pytest tests/test_database.py tests/test_settings.py`
- **Lint Check**: Run `uv run ruff check src/database.py src/settings_handler.py`
- **Manual Verification**:
  1. Add a video to favorites (`Ctrl+B`).
  2. Restart HexPlayer and check Favorites dialog (`Ctrl+Shift+B`).
  3. Verify resume prompt appears when reopening a partially watched video.
