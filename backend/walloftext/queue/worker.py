"""Persistent print queue with a single worker thread (BUILD_PLAN 6.3, 6.4, 6.5).

States: held → queued → printing → done | failed | cancelled. "missed" rows are
History-only entries for schedules that were skipped.
"""
from __future__ import annotations

import io
import json
import logging
import threading
import time
from typing import Any, Callable

from PIL import Image

from ..events import EventBus
from ..printer.base import Cancelled
from ..store.db import Store

log = logging.getLogger(__name__)

DEFAULT_ROLL_M = 10.0  # a common 58 mm roll; set the real length in Settings › Printer › Paper
NOMINAL_MM_PER_ROW = 0.125  # 203 dpi = 8 dot rows per mm; Settings › Printer › Calibrate refines it
FEED_ROWS = 24 * 3


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("1").save(buf, "PNG", optimize=True)
    return buf.getvalue()


class PrintQueue:
    def __init__(self, store: Store, printer, events: EventBus, settings_get: Callable[[], dict],
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.printer = printer
        self.events = events
        self.settings_get = settings_get
        self.clock = clock
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._cancel_ids: set[int] = set()
        self._thread: threading.Thread | None = None
        self.active_id: int | None = None
        self.active_progress = 0
        self._last_status: str | None = None
        self.on_done: list[Callable[[dict], None]] = []

    # ------------------------------------------------------------ jobs --
    def enqueue(self, image: Image.Image, source: str, title: str, document: dict | None = None,
                copies: int = 1, held_until: float | None = None, meta: dict | None = None) -> int:
        c = self.store.conn()
        cur = c.execute(
            "INSERT INTO jobs(source,title,state,created_at,document,bitmap,copies,rows,held_until,meta,progress) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            (source, title[:120], "held" if held_until else "queued", self.clock(),
             json.dumps(document) if document is not None else None, _png(image), max(1, min(10, copies)),
             image.height, held_until, json.dumps(meta or {})),
        )
        job_id = cur.lastrowid
        self._publish(job_id)
        self._wake.set()
        return job_id

    def log_missed(self, source: str, title: str, reason: str, meta: dict | None = None) -> int:
        cur = self.store.conn().execute(
            "INSERT INTO jobs(source,title,state,error,created_at,finished_at,meta,progress) VALUES(?,?,?,?,?,?,?,0)",
            (source, title[:120], "missed", reason, self.clock(), self.clock(), json.dumps(meta or {})),
        )
        self._publish(cur.lastrowid)
        return cur.lastrowid

    def get(self, job_id: int, with_blobs: bool = False) -> dict | None:
        cols = "*" if with_blobs else ("id,source,title,state,error,created_at,finished_at,progress,copies,rows,"
                                       "held_until,meta,started_at")
        row = self.store.conn().execute(f"SELECT {cols} FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def _row(self, row) -> dict:
        d = dict(row)
        if "meta" in d:
            try:
                d["meta"] = json.loads(d["meta"] or "{}")
            except ValueError:
                d["meta"] = {}
        if d.get("document"):
            d["document"] = json.loads(d["document"])
        d["has_image"] = d.get("rows") is not None
        return d

    def list(self, states: tuple[str, ...] | None = None, source: str | None = None, limit: int = 50,
             before_id: int | None = None, search: str | None = None) -> list[dict]:
        q = ("SELECT id,source,title,state,error,created_at,finished_at,progress,copies,rows,held_until,meta,"
             "started_at FROM jobs WHERE 1=1")
        args: list[Any] = []
        if states:
            q += f" AND state IN ({','.join('?' * len(states))})"
            args += states
        if source:
            q += " AND source=?"
            args.append(source)
        if before_id:
            q += " AND id<?"
            args.append(before_id)
        if search:
            q += " AND (title LIKE ? ESCAPE '\\' OR document LIKE ? ESCAPE '\\')"
            like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [like, like]
        q += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(500, limit)))
        return [self._row(r) for r in self.store.conn().execute(q, args).fetchall()]

    def pending(self) -> list[dict]:
        rows = self.list(("held", "queued", "printing"), limit=200)
        return sorted(rows, key=lambda r: r["id"])

    def image_png(self, job_id: int) -> bytes | None:
        row = self.store.conn().execute("SELECT bitmap FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row[0] if row and row[0] else None

    def cancel(self, job_id: int) -> bool:
        c = self.store.conn()
        row = c.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return False
        if row[0] in ("queued", "held"):
            c.execute("UPDATE jobs SET state='cancelled', finished_at=? WHERE id=?", (self.clock(), job_id))
            self._publish(job_id)
            return True
        if row[0] == "printing":
            self._cancel_ids.add(job_id)
            return True
        return False

    def cancel_all(self) -> int:
        n = 0
        for j in self.pending():
            n += self.cancel(j["id"])
        return n

    def retry(self, job_id: int, source: str | None = None) -> int | None:
        row = self.store.conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or not row["bitmap"]:
            return None
        img = Image.open(io.BytesIO(row["bitmap"])).convert("1")
        doc = json.loads(row["document"]) if row["document"] else None
        return self.enqueue(img, source or row["source"], row["title"], doc, row["copies"] or 1)

    def release_held(self, before: float | None = None) -> int:
        """Quiet hours ended: held jobs become queued."""
        now = before or self.clock()
        c = self.store.conn()
        ids = [r[0] for r in c.execute("SELECT id FROM jobs WHERE state='held' AND held_until<=?", (now,))]
        for i in ids:
            c.execute("UPDATE jobs SET state='queued' WHERE id=?", (i,))
            self._publish(i)
        if ids:
            self._wake.set()
        return len(ids)

    def delete(self, job_id: int) -> bool:
        cur = self.store.conn().execute(
            "DELETE FROM jobs WHERE id=? AND state NOT IN ('printing','queued','held')", (job_id,))
        return cur.rowcount > 0

    def _clear_printed_list(self, job: dict) -> None:
        """A List print removes the items it printed, once it is on paper. Items added
        while it was waiting or printing stay; a failed print leaves the list alone."""
        try:
            meta = json.loads(job.get("meta") or "{}") or {}
        except (TypeError, ValueError):
            return
        ids = [int(i) for i in meta.get("clear_list_items") or [] if str(i).isdigit()]
        if not ids:
            return
        self.store.conn().execute(f"DELETE FROM list_items WHERE id IN ({','.join('?' * len(ids))})", ids)
        self.events.publish("list", {"list": meta.get("list", "shopping")})

    def clear_history(self) -> int:
        return self.store.conn().execute(
            "DELETE FROM jobs WHERE state NOT IN ('printing','queued','held')").rowcount

    def prune(self) -> int:
        h = self.settings_get().get("history", {})
        max_items = int(h.get("max_items", 200) or 0)  # 0 = no limit
        max_days = float(h.get("max_days", 30) or 0)  # 0 = no limit
        c = self.store.conn()
        n = 0
        if max_days > 0:
            cutoff = self.clock() - max_days * 86400
            n += c.execute("DELETE FROM jobs WHERE state NOT IN ('printing','queued','held') AND created_at<?",
                           (cutoff,)).rowcount
        if max_items > 0:
            n += c.execute(
                "DELETE FROM jobs WHERE state NOT IN ('printing','queued','held') AND id NOT IN "
                "(SELECT id FROM jobs WHERE state NOT IN ('printing','queued','held') ORDER BY id DESC LIMIT ?)",
                (max_items,)).rowcount
        return n

    def count_today(self, sources: tuple[str, ...]) -> int:
        lt = time.localtime(self.clock())
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        q = (f"SELECT COUNT(*) FROM jobs WHERE created_at>=? AND state NOT IN ('cancelled','missed') "
             f"AND source IN ({','.join('?' * len(sources))})")
        return self.store.conn().execute(q, (midnight, *sources)).fetchone()[0]

    # ---------------------------------------------------------- printer --
    def paper_used_mm(self) -> float:
        rows = int(self.store.get("rows_since_new_roll", "0") or 0)
        mm_per_row = float(self.settings_get().get("printer", {}).get("mm_per_row") or NOMINAL_MM_PER_ROW)
        return rows * mm_per_row

    def roll_mm(self) -> float:
        return float(self.settings_get().get("printer", {}).get("roll_length_m") or DEFAULT_ROLL_M) * 1000

    def paper_percent(self) -> int:
        return max(0, min(100, round(100 - self.paper_used_mm() * 100 / self.roll_mm())))

    def paper_left_m(self) -> float:
        return max(0.0, round((self.roll_mm() - self.paper_used_mm()) / 1000, 1))

    def new_roll(self) -> None:
        self.store.set("rows_since_new_roll", "0")
        self.set_paper_out(False)

    def set_paper_out(self, out: bool) -> None:
        self.store.set("paper_out", "1" if out else "0")
        self._publish_status()
        if not out:
            self._wake.set()

    def status(self) -> dict:
        drv = self.printer.status()
        state = drv.state
        if getattr(self.printer, "detects_paper", False):
            # The sensor is the truth. Paper back after running out = a new roll: reset the estimate.
            was_out = self.store.get("paper_out_sensor", "0") == "1"
            now_out = state == "paper_out"
            if now_out != was_out:
                self.store.set("paper_out_sensor", "1" if now_out else "0")
                if was_out and not now_out:
                    self.store.set("rows_since_new_roll", "0")
                    self.store.set("paper_out", "0")
                    self._wake.set()
        if state == "ready" and self.store.get("paper_out", "0") == "1":
            state = "paper_out"
        if state == "ready" and self.active_id is not None:
            state = "printing"
        pend = self.pending()
        return {
            "state": state,
            "detail": drv.detail,
            "paper_percent": self.paper_percent(),
            "paper_left_m": self.paper_left_m(),
            "queue_length": sum(1 for j in pend if j["state"] in ("queued", "printing")),
            "held": sum(1 for j in pend if j["state"] == "held"),
            "active": {"id": self.active_id, "progress": self.active_progress} if self.active_id else None,
        }

    def _publish(self, job_id: int) -> None:
        j = self.get(job_id)
        if j:
            self.events.publish("job", j)

    def _publish_status(self) -> None:
        st = self.status()
        self.events.publish("printer", st)
        self._last_status = st["state"]

    # ----------------------------------------------------------- worker --
    def recover(self) -> None:
        c = self.store.conn()
        c.execute("UPDATE jobs SET state='failed', error='interrupted', finished_at=? WHERE state='printing'",
                  (self.clock(),))

    def start(self) -> None:
        self.recover()
        self._thread = threading.Thread(target=self._run, name="print-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def kick(self) -> None:
        self._wake.set()

    def _next(self) -> dict | None:
        row = self.store.conn().execute(
            "SELECT * FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None

    def _run(self) -> None:
        last_prune = 0.0
        while not self._stop.is_set():
            try:
                if self.clock() - last_prune > 3600:
                    self.prune()
                    last_prune = self.clock()
                self.release_held()
                st = self.status()
                if st["state"] != self._last_status:
                    self._publish_status()
                job = self._next()
                if job and st["state"] == "ready":
                    self._print(job)
                    continue
            except Exception:
                log.exception("print worker error")
            self._wake.wait(timeout=5 if not self._next() else 2)
            self._wake.clear()

    def _print(self, job: dict) -> None:
        c = self.store.conn()
        jid = job["id"]
        c.execute("UPDATE jobs SET state='printing', started_at=?, progress=0 WHERE id=?", (self.clock(), jid))
        self.active_id, self.active_progress = jid, 0
        self._publish(jid)
        self._publish_status()
        img = Image.open(io.BytesIO(job["bitmap"])).convert("1")
        pset = self.settings_get().get("printer", {})
        if pset.get("rotate_180", True):
            # The printer hangs so paper reads upside down; turn the slip round. Preview and History
            # keep the upright bitmap; only what goes to the printer is rotated (exact for 1-bit).
            img = img.transpose(Image.Transpose.ROTATE_180)
        extra = int(pset.get("extra_feed", 0)) + int((json.loads(job.get("meta") or "{}") or {}).get("extra_feed", 0))
        last_pub = [0.0]

        def progress(p: int) -> None:
            self.active_progress = p
            now = time.monotonic()
            if now - last_pub[0] > 0.15 or p >= 100:
                last_pub[0] = now
                c2 = self.store.conn()
                c2.execute("UPDATE jobs SET progress=? WHERE id=?", (p, jid))
                self.events.publish("progress", {"id": jid, "progress": p})

        def should_cancel() -> bool:
            return jid in self._cancel_ids

        state, err = "done", None
        if hasattr(self.printer, "set_speed"):
            self.printer.set_speed(pset.get("speed", "normal"))
        try:
            self.printer.print_bitmap(img, copies=job["copies"] or 1, extra_feed=extra,
                                      on_progress=progress, should_cancel=should_cancel,
                                      density=int(pset.get("darkness", 120)))
        except Cancelled:
            state = "cancelled"
        except FileNotFoundError as exc:
            state, err = "failed", f"offline: {exc}"
        except OSError as exc:
            state, err = "failed", f"offline: {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("print failed")
            state, err = "failed", str(exc)[:200]
        self._cancel_ids.discard(jid)
        if state == "done" and getattr(self.printer, "detects_paper", False):
            time.sleep(0.3)
            if self.printer.status().state == "paper_out":
                state, err = "failed", "paper_out"
        rows = img.height * (job["copies"] or 1) + FEED_ROWS + 24 * extra
        if state in ("done", "cancelled"):
            used = int(self.store.get("rows_since_new_roll", "0") or 0) + rows
            self.store.set("rows_since_new_roll", str(used))
        c.execute("UPDATE jobs SET state=?, error=?, finished_at=?, progress=? WHERE id=?",
                  (state, err, self.clock(), 100 if state == "done" else self.active_progress, jid))
        if state == "done":
            self._clear_printed_list(job)
        self.active_id = None
        self._publish(jid)
        self._publish_status()
        done = self.get(jid)
        for cb in self.on_done:
            try:
                cb(done)
            except Exception:
                log.exception("on_done hook failed")
