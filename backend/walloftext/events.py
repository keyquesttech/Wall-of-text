"""In-process pub/sub feeding `/api/events` (SSE). Safe to publish from any thread."""
from __future__ import annotations

import asyncio
import json
from typing import Callable


class EventBus:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.listeners: list[Callable[[str, dict], None]] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: str, data: dict) -> None:
        for cb in list(self.listeners):
            try:
                cb(event, data)
            except Exception:
                pass
        msg = {"event": event, "data": json.dumps(data, default=str)}
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None or self.loop is None:
            self._deliver(msg)
        else:
            try:
                self.loop.call_soon_threadsafe(self._deliver, msg)
            except RuntimeError:  # loop closed (shutdown)
                pass

    def _deliver(self, msg: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow client; it will catch up through polling
