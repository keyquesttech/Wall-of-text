"""The Telegram bot side of remote messages: commands, buttons, and asking how to print.

Only allowed senders reach this (the pipeline drops everyone else first).

* Built-in commands: /help (/start), /settings (pick your default print style and size with
  buttons), /templates (tap one to get its text back in a block that copies with one tap),
  /cancel (drop a message that's waiting for your choice).
* Custom commands (Settings › Telegram): reply with text, run a print action (weather,
  fortune, a routine...), or set how the next message prints ("/big Hello" prints at once).
* "Ask how to print": after each message the bot answers with buttons for the style and size,
  then Print or Cancel. With no answer it prints with the defaults (or doesn't) after a while.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING

from .base import Attachment, InboundMessage

if TYPE_CHECKING:
    from .pipeline import Pipeline

log = logging.getLogger(__name__)

STYLES = {"message": "Message slip", "plain": "Plain text", "big": "Big text", "checklist": "Checklist"}
SHORT = {"message": "Slip", "plain": "Plain", "big": "Big", "checklist": "List"}
SIZES = ("S", "M", "L", "XL")
BUILTINS = {
    "help": "What I can do",
    "settings": "How your messages print",
    "templates": "Get a message to copy and fill in",
    "cancel": "Don't print the message waiting for you",
}
NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
PENDING_KEY = "telegram_pending"
PREFS_KEY = "telegram_prefs"


def valid_commands(cfg: dict) -> list[dict]:
    """The custom commands that can be used: valid names, no clash with the built-ins or each other."""
    out, seen = [], set(BUILTINS) | {"start"}
    for c in cfg.get("commands") or []:
        name = str(c.get("name", "")).lstrip("/").lower()
        if NAME_RE.match(name) and name not in seen and c.get("type") in ("reply", "action", "style"):
            seen.add(name)
            out.append({**c, "name": name})
    return out


class Bot:
    def __init__(self, pipeline: "Pipeline"):
        self.p = pipeline
        self.svc = pipeline.svc

    # ------------------------------------------------------------ settings --
    def cfg(self) -> dict:
        return self.svc.app_settings.get("telegram")

    def _load(self, key: str) -> dict:
        try:
            return json.loads(self.svc.store.get(key, "{}") or "{}")
        except ValueError:
            return {}

    def _save(self, key: str, value: dict) -> None:
        self.svc.store.set(key, json.dumps(value))

    def prefs(self, sender_id: str) -> dict:
        d = self.cfg().get("defaults") or {}
        base = {"style": d.get("style", "message"), "size": d.get("size", "M")}
        mine = self._load(PREFS_KEY).get(sender_id) or {}
        return {**base, **{k: v for k, v in mine.items() if k in ("style", "size")}}

    def _set_pref(self, sender_id: str, **kw) -> dict:
        all_ = self._load(PREFS_KEY)
        all_[sender_id] = {**(all_.get(sender_id) or {}), **kw}
        self._save(PREFS_KEY, all_)
        return self.prefs(sender_id)

    def options_for(self, sender: dict) -> dict:
        """This sender's style and size, plus a one-off from a style command like /big."""
        opts = self.prefs(sender["id"])
        all_ = self._load(PREFS_KEY)
        nxt = (all_.get(sender["id"]) or {}).pop("next", None)
        if nxt:
            self._save(PREFS_KEY, all_)
            opts.update({k: v for k, v in nxt.items() if k in ("style", "size")})
        return opts

    def menu(self) -> list[tuple[str, str]]:
        return [(k, v) for k, v in BUILTINS.items()] + [(c["name"], c.get("description") or c["name"])
                                                       for c in valid_commands(self.cfg())]

    # ------------------------------------------------------------ commands --
    async def on_command(self, msg: InboundMessage, sender: dict, adapter) -> str:
        word, _, rest = msg.body[1:].partition(" ")
        name, rest = word.split("@")[0].lower(), rest.strip()
        chat = msg.reply
        if name in ("start", "help"):
            lines = [f"Hi {sender['name']}! Send me a message and I print it on the wall.", ""]
            lines += [f"/{c} · {d}" for c, d in self.menu()]
            await adapter.send(chat, "\n".join(lines))
            return "command"
        if name == "settings":
            await adapter.send(chat, self._settings_text(sender), self._settings_buttons(sender))
            return "command"
        if name == "templates":
            tpls = [t for t in self.cfg().get("templates") or [] if (t.get("text") or "").strip()]
            if not tpls:
                await adapter.send(chat, "No templates yet. They're added in the app: Settings › Telegram.")
            else:
                await adapter.send(chat, "Tap one and I'll send it back to copy:",
                                   [[(t.get("name") or f"Template {i + 1}", f"tpl:{i}")] for i, t in enumerate(tpls)][:20])
            return "command"
        if name == "cancel":
            n = self._drop_pending(sender["id"])
            await adapter.send(chat, "Cancelled. Nothing will print." if n else "Nothing is waiting.")
            return "command"
        cmd = next((c for c in valid_commands(self.cfg()) if c["name"] == name), None)
        if cmd is None:
            await adapter.send(chat, f"I don't know /{name}. Send /help for the list.")
            return "command"
        if cmd["type"] == "reply":
            await adapter.send(chat, cmd.get("text") or "…", code=bool(cmd.get("copyable")))
            return "command"
        if cmd["type"] == "action":
            if not self.p._rate_ok(sender["id"]):
                await adapter.send(chat, "That's a lot of prints. Try again later.")
                return "rate_limited"
            from .. import actions
            res = await actions.run(self.svc, cmd.get("action") or "none", source="Remote")
            await adapter.send(chat, res)
            return "command"
        # style: "/big Hello" prints now; "/big" applies to the next message
        style = {"style": cmd.get("style") or "message", "size": cmd.get("size") or "M"}
        if rest:
            if not self.p._rate_ok(sender["id"]):
                await adapter.send(chat, "That's a lot of prints. Try again later.")
                return "rate_limited"
            msg.body = rest
            return await self.p.deliver(msg, sender, {**self.prefs(sender["id"]), **style}, adapter)
        all_ = self._load(PREFS_KEY)
        all_.setdefault(sender["id"], {})["next"] = style
        self._save(PREFS_KEY, all_)
        await adapter.send(chat, f"Your next message prints as {STYLES[style['style']].lower()}, size {style['size']}.")
        return "command"

    def _settings_text(self, sender: dict) -> str:
        o = self.prefs(sender["id"])
        return f"How your messages print:\nStyle: {STYLES.get(o['style'], o['style'])} · Size: {o['size']}"

    def _settings_buttons(self, sender: dict) -> list:
        o = self.prefs(sender["id"])
        return self._option_rows(o, "set")

    @staticmethod
    def _option_rows(o: dict, prefix: str) -> list:
        mark = lambda on, t: f"✓ {t}" if on else t  # noqa: E731
        return [[(mark(o["style"] == k, SHORT[k]), f"{prefix}:style:{k}") for k in STYLES],
                [(mark(o["size"] == s, s), f"{prefix}:size:{s}") for s in SIZES]]

    # ------------------------------------------------------------- buttons --
    async def on_callback(self, msg: InboundMessage, sender: dict, adapter) -> str:
        cb = msg.callback or {}
        data, chat, mid = cb.get("data", ""), msg.reply, cb.get("message_id")
        await adapter.answer(cb.get("id", ""))
        parts = data.split(":")
        if parts[0] == "set" and len(parts) == 3 and parts[1] in ("style", "size"):
            if (parts[1] == "style" and parts[2] in STYLES) or (parts[1] == "size" and parts[2] in SIZES):
                self._set_pref(sender["id"], **{parts[1]: parts[2]})
            await adapter.edit(chat, mid, self._settings_text(sender), self._settings_buttons(sender))
            return "command"
        if parts[0] == "tpl" and len(parts) == 2 and parts[1].isdigit():
            tpls = [t for t in self.cfg().get("templates") or [] if (t.get("text") or "").strip()]
            i = int(parts[1])
            if i < len(tpls):
                await adapter.send(chat, tpls[i]["text"], code=True)
                await adapter.send(chat, "Copy it, fill it in and send it back to print.")
            return "command"
        if parts[0] == "p" and len(parts) >= 3:
            return await self._pending_tap(parts[1], parts[2:], sender, chat, mid, adapter)
        return "command"

    # ------------------------------------------------- asking how to print --
    def _pending(self) -> dict:
        return self._load(PENDING_KEY)

    def _drop_pending(self, sender_id: str) -> int:
        pend = self._pending()
        mine = [k for k, v in pend.items() if v["sender_id"] == sender_id]
        for k in mine:
            pend.pop(k)
        self._save(PENDING_KEY, pend)
        return len(mine)

    @staticmethod
    def _freeze(msg: InboundMessage) -> dict:
        return {"channel": msg.channel, "sender_id": msg.sender_id, "sender_name": msg.sender_name, "body": msg.body,
                "external_id": msg.external_id, "received_at": msg.received_at, "subject": msg.subject,
                "reply": msg.reply, "attachments": [{"f": a.filename, "t": a.content_type,
                                                    "d": base64.b64encode(a.data).decode()} for a in msg.attachments[:1]]}

    @staticmethod
    def _thaw(d: dict) -> InboundMessage:
        return InboundMessage(channel=d["channel"], sender_id=d["sender_id"], sender_name=d["sender_name"], body=d["body"],
                              external_id=d["external_id"], received_at=d["received_at"], subject=d.get("subject"),
                              reply=d.get("reply"),
                              attachments=[Attachment(a["f"], a["t"], base64.b64decode(a["d"])) for a in d.get("attachments", [])])

    def _prompt(self, opts: dict, waited: str | None = None) -> str:
        cfg = self.cfg()
        mins = max(1, int(cfg.get("ask_timeout_s", 120)) // 60)
        after = "prints like this" if cfg.get("on_timeout", "print") == "print" else "won't print"
        return (f"How should this print?\nStyle: {STYLES.get(opts['style'])} · Size: {opts['size']}\n"
                f"(No answer in {mins} min: it {after}.)") if waited is None else waited

    async def ask(self, msg: InboundMessage, sender: dict, opts: dict, adapter) -> str:
        token = uuid.uuid4().hex[:8]
        rows = self._option_rows(opts, f"p:{token}") + [[("🖨 Print", f"p:{token}:go"), ("Cancel", f"p:{token}:no")]]
        mid = await adapter.send(msg.reply, self._prompt(opts), rows)
        pend = self._pending()
        pend[token] = {"msg": self._freeze(msg), "sender_id": sender["id"], "opts": opts, "created": time.time(),
                       "chat": msg.reply, "prompt": mid}
        self._save(PENDING_KEY, pend)
        self.p.mark_seen(msg, "asking")
        return "asking"

    async def _pending_tap(self, token: str, rest: list[str], sender: dict, chat, mid, adapter) -> str:
        pend = self._pending()
        item = pend.get(token)
        if not item or item["sender_id"] != sender["id"]:
            await adapter.edit(chat, mid, "This message has already been printed or cancelled.")
            return "command"
        opts = item["opts"]
        if rest[0] in ("style", "size") and len(rest) == 2:
            if (rest[0] == "style" and rest[1] in STYLES) or (rest[0] == "size" and rest[1] in SIZES):
                opts[rest[0]] = rest[1]
            pend[token] = item
            self._save(PENDING_KEY, pend)
            rows = self._option_rows(opts, f"p:{token}") + [[("🖨 Print", f"p:{token}:go"), ("Cancel", f"p:{token}:no")]]
            await adapter.edit(chat, mid, self._prompt(opts), rows)
            return "command"
        pend.pop(token)
        self._save(PENDING_KEY, pend)
        if rest[0] == "no":
            await adapter.edit(chat, mid, "Cancelled. Nothing printed.")
            return "cancelled"
        await adapter.edit(chat, mid, f"Printing as {STYLES[opts['style']].lower()}, size {opts['size']}.")
        return await self.p.deliver(self._thaw(item["msg"]), self.p.senders.get(item["sender_id"]) or sender, opts, adapter)

    async def expire(self, adapter) -> int:
        """Messages nobody answered: print with the chosen settings, or drop them (Settings)."""
        cfg = self.cfg()
        timeout = max(30, int(cfg.get("ask_timeout_s", 120)))
        pend = self._pending()
        due = [k for k, v in pend.items() if time.time() - v["created"] > timeout]
        for k in due:
            item = pend.pop(k)
            self._save(PENDING_KEY, pend)
            if cfg.get("on_timeout", "print") == "print":
                sender = self.p.senders.get(item["sender_id"])
                if sender is None:
                    continue
                await adapter.edit(item["chat"], item["prompt"], f"No answer, so printing as {STYLES[item['opts']['style']].lower()}, "
                                                                f"size {item['opts']['size']}.")
                await self.p.deliver(self._thaw(item["msg"]), sender, item["opts"], adapter)
            else:
                await adapter.edit(item["chat"], item["prompt"], "No answer, so it wasn't printed.")
        return len(due)
