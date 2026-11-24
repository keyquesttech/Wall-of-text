"""SQLite store in WAL mode with forward-only migrations (section 6.4)."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: sessions and key-value settings
    """
    CREATE TABLE sessions (
        token TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        last_seen REAL NOT NULL,
        user_agent TEXT
    );
    CREATE TABLE kv (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    # 2: print jobs (used by the queue from Phase 2; setup slips use it now)
    """
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        state TEXT NOT NULL,
        error TEXT,
        created_at REAL NOT NULL,
        finished_at REAL,
        document TEXT,
        bitmap BLOB
    );
    """,
    # 3: queue/history columns
    """
    ALTER TABLE jobs ADD COLUMN progress INTEGER DEFAULT 0;
    ALTER TABLE jobs ADD COLUMN copies INTEGER DEFAULT 1;
    ALTER TABLE jobs ADD COLUMN rows INTEGER;
    ALTER TABLE jobs ADD COLUMN held_until REAL;
    ALTER TABLE jobs ADD COLUMN started_at REAL;
    ALTER TABLE jobs ADD COLUMN meta TEXT;
    CREATE INDEX jobs_state ON jobs(state);
    CREATE INDEX jobs_source ON jobs(source);
    """,
    # 4: schedules and routines
    """
    CREATE TABLE schedules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        time TEXT,
        days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
        sections TEXT NOT NULL DEFAULT '[]',
        conditions TEXT NOT NULL DEFAULT '[]',
        icon TEXT,
        created_at REAL NOT NULL,
        last_due REAL,
        last_run_at REAL,
        last_result TEXT
    );
    """,
    # 5: shared approval list (guest notes + remote messages)
    """
    CREATE TABLE inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        sender TEXT NOT NULL,
        channel TEXT NOT NULL,
        title TEXT NOT NULL,
        document TEXT NOT NULL,
        preview TEXT,
        state TEXT NOT NULL,
        created_at REAL NOT NULL,
        decided_at REAL,
        meta TEXT
    );
    CREATE INDEX inbox_state ON inbox(state);
    """,
    # 6: remote messages
    """
    CREATE TABLE remote_senders (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        identifiers TEXT NOT NULL,
        approval TEXT NOT NULL DEFAULT 'print',
        created_at REAL NOT NULL
    );
    CREATE TABLE remote_seen (
        external_id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        seen_at REAL NOT NULL,
        outcome TEXT NOT NULL
    );
    CREATE INDEX remote_seen_at ON remote_seen(seen_at);
    """,
    # 7: templates and shared lists
    """
    CREATE TABLE templates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        icon TEXT,
        document TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE list_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list TEXT NOT NULL,
        text TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL DEFAULT 0,
        added_by TEXT,
        created_at REAL NOT NULL,
        done_at REAL
    );
    CREATE INDEX list_items_list ON list_items(list);
    """,
    # Google Tasks was removed: drop its blocks and its "Only if any are due" condition from saved
    # schedules, and switch off any schedule that printed nothing else.
    """
    UPDATE schedules SET enabled = 0
    WHERE EXISTS (SELECT 1 FROM json_each(schedules.sections) WHERE json_extract(value, '$.type') = 'tasks')
      AND NOT EXISTS (SELECT 1 FROM json_each(schedules.sections) WHERE json_extract(value, '$.type') IS NOT 'tasks');
    UPDATE schedules SET sections = (SELECT json_group_array(json(value)) FROM json_each(schedules.sections)
                                     WHERE json_extract(value, '$.type') IS NOT 'tasks')
    WHERE EXISTS (SELECT 1 FROM json_each(schedules.sections) WHERE json_extract(value, '$.type') = 'tasks');
    UPDATE schedules SET conditions = (SELECT json_group_array(json(value)) FROM json_each(schedules.conditions)
                                       WHERE json_extract(value, '$.type') IS NOT 'has_tasks')
    WHERE EXISTS (SELECT 1 FROM json_each(schedules.conditions) WHERE json_extract(value, '$.type') = 'has_tasks');
    UPDATE schedules SET icon = NULL WHERE icon = 'tasks';
    """,
    # 9: one-off schedules (a single date instead of week days)
    """
    ALTER TABLE schedules ADD COLUMN once_on TEXT;
    """,
]


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._mem_conn: sqlite3.Connection | None = None
        self.migrate()

    def conn(self) -> sqlite3.Connection:
        if self.path == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
                self._mem_conn.row_factory = sqlite3.Row
            return self._mem_conn
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    def migrate(self) -> None:
        c = self.conn()
        version = c.execute("PRAGMA user_version").fetchone()[0]
        for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            c.execute("BEGIN")
            try:
                for statement in _split(sql):
                    c.execute(statement)
                c.execute(f"PRAGMA user_version={i}")
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        self.conn().execute(
            "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def delete(self, key: str) -> None:
        self.conn().execute("DELETE FROM kv WHERE key=?", (key,))


def _split(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]
