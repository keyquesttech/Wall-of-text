"""The shared "Waiting for your OK" list for guest notes and remote messages
(BUILD_PLAN 10.3). Approving prints the stored document with the item's source."""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..services import Services


class Inbox:
    def __init__(self, svc: "Services"):
        self.svc = svc

    def _row(self, r) -> dict:
        d = dict(r)
        d["document"] = json.loads(d["document"]) if d.get("document") else None
        d["meta"] = json.loads(d["meta"] or "{}")
        return d

    def add(self, source: str, sender: str, channel: str, title: str, document: dict, preview_text: str,
            meta: dict | None = None) -> int:
        cur = self.svc.store.conn().execute(
            "INSERT INTO inbox(source,sender,channel,title,document,preview,state,created_at,meta) "
            "VALUES(?,?,?,?,?,?, 'waiting', ?, ?)",
            (source, sender[:80], channel, title[:120], json.dumps(document), preview_text[:400], time.time(),
             json.dumps(meta or {})))
        self.publish()
        return cur.lastrowid

    def waiting(self) -> list[dict]:
        rows = self.svc.store.conn().execute(
            "SELECT * FROM inbox WHERE state='waiting' ORDER BY id").fetchall()
        return [self._row(r) for r in rows]

    def count(self) -> int:
        return self.svc.store.conn().execute("SELECT COUNT(*) FROM inbox WHERE state='waiting'").fetchone()[0]

    def get(self, iid: int) -> dict | None:
        r = self.svc.store.conn().execute("SELECT * FROM inbox WHERE id=?", (iid,)).fetchone()
        return self._row(r) if r else None

    def approve(self, iid: int) -> int | None:
        item = self.get(iid)
        if not item or item["state"] != "waiting":
            return None
        sched = self.svc.extras.get("scheduler")
        held = sched.hold_until() if sched else None
        jid = self.svc.print_document(item["document"], item["source"], item["title"], held_until=held,
                                      meta={**item["meta"], "inbox_id": iid, "approved": True})
        self.svc.store.conn().execute("UPDATE inbox SET state='approved', decided_at=? WHERE id=?", (time.time(), iid))
        self.publish()
        return jid

    def decline(self, iid: int) -> bool:
        n = self.svc.store.conn().execute(
            "UPDATE inbox SET state='declined', decided_at=? WHERE id=? AND state='waiting'", (time.time(), iid)).rowcount
        self.publish()
        return n > 0

    def prune(self, days: int = 30) -> None:
        self.svc.store.conn().execute("DELETE FROM inbox WHERE state<>'waiting' AND created_at<?",
                                      (time.time() - days * 86400,))

    def publish(self) -> None:
        self.svc.events.publish("inbox", {"waiting": self.count()})
