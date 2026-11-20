"""Server-side sessions and the login rate limiter (section 10.2)."""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..store.db import Store

COOKIE_NAME = "wot_session"
REMEMBER_S = 30 * 24 * 3600
SHORT_S = 12 * 3600  # "remember" off: cookie dies with the browser, server row after 12 h


def passwords_match(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


class SessionStore:
    def __init__(self, store: Store, clock: Callable[[], float] = time.time):
        self.store = store
        self.clock = clock

    def create(self, remember: bool, user_agent: str | None = None) -> tuple[str, int]:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        ttl = REMEMBER_S if remember else SHORT_S
        self.store.conn().execute(
            "INSERT INTO sessions(token,created_at,expires_at,last_seen,user_agent) VALUES(?,?,?,?,?)",
            (token, now, now + ttl, now, (user_agent or "")[:200]),
        )
        return token, ttl

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        row = self.store.conn().execute("SELECT expires_at FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return False
        if row[0] < self.clock():
            self.revoke(token)
            return False
        return True

    def revoke(self, token: str) -> None:
        self.store.conn().execute("DELETE FROM sessions WHERE token=?", (token,))

    def revoke_all(self, except_token: str | None = None) -> None:
        if except_token:
            self.store.conn().execute("DELETE FROM sessions WHERE token<>?", (except_token,))
        else:
            self.store.conn().execute("DELETE FROM sessions")

    def purge_expired(self) -> None:
        self.store.conn().execute("DELETE FROM sessions WHERE expires_at<?", (self.clock(),))


@dataclass
class _Bucket:
    failures: int = 0
    locked_until: float = 0.0
    lock_s: float = 0.0


class LoginLimiter:
    """5 wrong attempts per client → 60 s lockout, doubling up to 15 min."""

    MAX_FAILURES = 5
    FIRST_LOCK = 60.0
    MAX_LOCK = 15 * 60.0

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._b: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def retry_after(self, client: str) -> float:
        with self._lock:
            b = self._b.get(client)
            if not b:
                return 0.0
            return max(0.0, b.locked_until - self.clock())

    def failure(self, client: str) -> float:
        with self._lock:
            b = self._b.setdefault(client, _Bucket())
            b.failures += 1
            if b.failures >= self.MAX_FAILURES:
                b.lock_s = self.FIRST_LOCK if b.lock_s == 0 else min(b.lock_s * 2, self.MAX_LOCK)
                b.locked_until = self.clock() + b.lock_s
                b.failures = 0
                return b.lock_s
            return 0.0

    def success(self, client: str) -> None:
        with self._lock:
            self._b.pop(client, None)
