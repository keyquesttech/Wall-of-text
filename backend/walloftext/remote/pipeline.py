"""One pipeline for every channel (BUILD_PLAN 9.2):

    dedupe → allow-list (+ email spoof check) → rate limit → clean → approval
    → daily limit → quiet hours → render → queue → acknowledgement

Unknown senders are dropped and counted, never printed.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from .base import InboundMessage, cap

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)

CHANNEL_LABEL = {"email": "Email", "telegram": "Telegram", "sms": "SMS", "mock": "Test"}


class Senders:
    def __init__(self, svc: "Services"):
        self.svc = svc

    def _row(self, r) -> dict:
        d = dict(r)
        d["identifiers"] = json.loads(d["identifiers"] or "[]")
        return d

    def list(self) -> list[dict]:
        return [self._row(r) for r in self.svc.store.conn().execute("SELECT * FROM remote_senders ORDER BY name")]

    def get(self, sid: str) -> dict | None:
        r = self.svc.store.conn().execute("SELECT * FROM remote_senders WHERE id=?", (sid,)).fetchone()
        return self._row(r) if r else None

    @staticmethod
    def norm(channel: str, value: str) -> str:
        v = value.strip()
        if channel == "email":
            return v.lower()
        if channel == "sms":
            return "".join(ch for ch in v if ch.isdigit() or ch == "+")
        return v

    def save(self, data: dict, sid: str | None = None) -> dict:
        ids = [{"channel": i["channel"], "value": self.norm(i["channel"], i["value"])}
               for i in data.get("identifiers", []) if i.get("value", "").strip()]
        cur = self.get(sid) if sid else None
        name = (data.get("name") or (cur or {}).get("name") or "Someone")[:40]
        default_approval = "approve" if any(i["channel"] == "sms" for i in ids) else "print"
        approval = data.get("approval") or (cur or {}).get("approval") or default_approval
        c = self.svc.store.conn()
        if cur:
            c.execute("UPDATE remote_senders SET name=?, identifiers=?, approval=? WHERE id=?",
                      (name, json.dumps(ids if "identifiers" in data else cur["identifiers"]), approval, sid))
        else:
            sid = uuid.uuid4().hex[:10]
            c.execute("INSERT INTO remote_senders(id,name,identifiers,approval,created_at) VALUES(?,?,?,?,?)",
                      (sid, name, json.dumps(ids), approval, time.time()))
        return self.get(sid)

    def delete(self, sid: str) -> bool:
        return self.svc.store.conn().execute("DELETE FROM remote_senders WHERE id=?", (sid,)).rowcount > 0

    def find(self, channel: str, sender_id: str) -> dict | None:
        v = self.norm(channel, sender_id)
        for s in self.list():
            if any(i["channel"] == channel and i["value"] == v for i in s["identifiers"]):
                return s
        return None


class Pipeline:
    def __init__(self, svc: "Services"):
        self.svc = svc
        self.senders = Senders(svc)
        self._hits: dict[str, list[float]] = {}
        self._acks: dict[int, tuple] = {}
        from .bot import Bot
        self.bot = Bot(self)

    # ----------------------------------------------------------- state --
    def seen(self, external_id: str) -> bool:
        return self.svc.store.conn().execute(
            "SELECT 1 FROM remote_seen WHERE external_id=?", (external_id,)).fetchone() is not None

    def mark_seen(self, msg: InboundMessage, outcome: str) -> None:
        self.svc.store.conn().execute(
            "INSERT OR REPLACE INTO remote_seen(external_id,channel,seen_at,outcome) VALUES(?,?,?,?)",
            (msg.external_id, msg.channel, time.time(), outcome))

    def blocked_count(self, days: int = 7) -> int:
        return self.svc.store.conn().execute(
            "SELECT COUNT(*) FROM remote_seen WHERE outcome='blocked' AND seen_at>?",
            (time.time() - days * 86400,)).fetchone()[0]

    def _rate_ok(self, sender_id: str) -> bool:
        limit = int(self.svc.app_settings.get("remote").get("rate_per_hour", 10))
        now = time.time()
        hits = [t for t in self._hits.get(sender_id, []) if now - t < 3600]
        if len(hits) >= limit:
            self._hits[sender_id] = hits
            return False
        hits.append(now)
        self._hits[sender_id] = hits
        return True

    # -------------------------------------------------------- document --
    def document(self, msg: InboundMessage, name: str, opts: dict | None = None) -> dict:
        """The print for a message. Style "message" (default) is the message slip (PRINT_TEMPLATES 8b:
        subject in t-l, body in t-m, "… (cut)" when truncated); "plain", "big" and "checklist" are
        plain blocks like Create makes. `size` S/M/L/XL sets the body text size."""
        cfg = self.svc.app_settings.get("remote")
        opts = opts or {}
        style, size = opts.get("style", "message"), opts.get("size", "M")
        size = size if size in ("S", "M", "L", "XL") else "M"
        when = datetime.fromtimestamp(msg.received_at)
        body = ""
        if msg.body:
            body, _ = cap(msg.body, int(cfg.get("max_chars", 600)), int(cfg.get("max_lines", 40)))
        pic = None
        for a in msg.attachments[:1]:
            pic = f"data:{a.content_type};base64," + base64.b64encode(a.data).decode()
        if style not in ("plain", "big", "checklist"):
            data: dict = {"sender": name, "subject": (msg.subject or "")[:120], "now": when.isoformat(timespec="minutes")}
            if size != "M":
                data["size"] = size
            if body:
                data["body"] = body
            if pic:
                data["image_src"] = pic
            return {"blocks": [{"type": "slip", "template": "message", "data": data}]}
        blocks: list[dict] = [{"type": "text", "text": f"From {name} · {when:%H:%M}", "size": "S", "bold": True},
                              {"type": "divider"}]
        if msg.subject:
            blocks.append({"type": "text", "text": msg.subject[:120], "size": "L", "bold": True})
        if body and style == "big":
            blocks.append({"type": "heading", "text": body, "size": size if size in ("L", "XL") else "XL"})
        elif body and style == "checklist":
            items = [ln.strip().lstrip("-*•☐[] ").strip() for ln in body.splitlines()]
            blocks.append({"type": "checklist", "size": size, "items": [{"text": t} for t in items if t][:60]})
        elif body:
            blocks.append({"type": "text", "text": body, "size": size})
        if pic:
            blocks.append({"type": "image", "src": pic, "style": "photo"})
        return {"blocks": blocks}

    # ----------------------------------------------------------- handle --
    @staticmethod
    def _bot_capable(adapter) -> bool:
        return adapter is not None and hasattr(adapter, "send")

    async def handle(self, msg: InboundMessage, adapter=None) -> str:
        """Returns the outcome: duplicate | blocked | rate_limited | waiting | limit | held | printed | queued
        | command | asking | cancelled."""
        if self.seen(msg.external_id):
            return "duplicate"
        sender = self.senders.find(msg.channel, msg.sender_id)
        if sender is None or (msg.channel == "email" and not msg.authenticated):
            self.mark_seen(msg, "blocked")
            log.info("remote: dropped message from an unknown %s sender", msg.channel)
            self.svc.events.publish("remote", {"blocked_week": self.blocked_count()})
            return "blocked"
        bot = self._bot_capable(adapter)
        if msg.callback is not None:
            self.mark_seen(msg, "command")
            return await self.bot.on_callback(msg, sender, adapter) if bot else "command"
        if bot and msg.body.startswith("/") and not msg.attachments:
            self.mark_seen(msg, "command")
            return await self.bot.on_command(msg, sender, adapter)
        if not self._rate_ok(sender["id"]):
            self.mark_seen(msg, "rate_limited")
            return "rate_limited"
        opts = self.bot.options_for(sender)
        if bot and self.svc.app_settings.get("telegram").get("ask_options"):
            return await self.bot.ask(msg, sender, opts, adapter)
        return await self.deliver(msg, sender, opts, adapter)

    async def deliver(self, msg: InboundMessage, sender: dict, opts: dict | None = None, adapter=None) -> str:
        """After the checks: approval, daily limit, quiet hours, print, acknowledgement."""
        doc = self.document(msg, sender["name"], opts)
        title = f"From {sender['name']}" + (f": {msg.subject[:40]}" if msg.subject else "")
        meta = {"channel": msg.channel, "sender": sender["id"]}
        sched = self.svc.extras["scheduler"]
        if sender["approval"] == "approve":
            self.svc.extras["inbox"].add("Remote", sender["name"], CHANNEL_LABEL.get(msg.channel, msg.channel),
                                         title, doc, (msg.subject or msg.body or "(picture)")[:200], meta)
            self.mark_seen(msg, "waiting")
            await self._ack(adapter, msg, "Waiting for approval.")
            return "waiting"
        if sched.over_daily_limit():
            self.mark_seen(msg, "limit")
            self.svc.queue.log_missed("Remote", title, "The daily print limit was reached.", meta)
            await self._ack(adapter, msg, "Not printed: the daily limit was reached.")
            return "limit"
        held = sched.hold_until()
        self.mark_seen(msg, "printing")  # before queueing: a crash here loses at most one print, never doubles it
        try:
            jid = self.svc.print_document(doc, "Remote", title, held_until=held, meta=meta)
        except Exception:
            log.exception("remote: render failed")
            # keep the text, drop the picture
            for b in doc["blocks"]:
                (b.get("data") or {}).pop("image_src", None)
            doc["blocks"] = [b for b in doc["blocks"] if b.get("type") != "image"]
            jid = self.svc.print_document(doc, "Remote", title, held_until=held, meta=meta)
        self.mark_seen(msg, "held" if held else "printed")
        if held:
            await self._ack(adapter, msg, "Queued: it prints when quiet hours end.")
            return "held"
        st = self.svc.queue.status()["state"]
        if st in ("offline", "paper_out"):
            await self._ack(adapter, msg, "Queued: the printer is out of paper." if st == "paper_out"
                            else "Queued: the printer is offline.")
            return "queued"
        if adapter is not None:
            self._acks[jid] = (adapter, msg)
        return "printed"

    async def _ack(self, adapter, msg: InboundMessage, text: str) -> None:
        if adapter is None:
            return
        try:
            await adapter.ack(msg, text)
        except Exception:
            log.warning("remote: acknowledgement failed")

    def on_job_done(self, job: dict) -> None:
        """Queue hook (worker thread): send "Printed" once the job really came out."""
        pair = self._acks.pop(job["id"], None)
        if not pair or self.svc.loop is None:
            return
        adapter, msg = pair
        text = "Printed." if job["state"] == "done" else "Didn't print. It's in History."
        import asyncio

        asyncio.run_coroutine_threadsafe(self._ack(adapter, msg, text), self.svc.loop)
