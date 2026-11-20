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
