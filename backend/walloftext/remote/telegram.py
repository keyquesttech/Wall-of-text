"""Telegram bot via long-polled getUpdates: outbound only, works behind any home
router (BUILD_PLAN 9.2). Plain httpx, no SDK. The bot token lives in secrets.json."""
from __future__ import annotations

import time

import httpx

from .base import Attachment, ChannelError, InboundMessage
from .secrets import Secrets

API = "https://api.telegram.org"
MAX_PHOTO = 8 * 1024 * 1024


class TelegramAdapter:
    id = "telegram"
    label = "Telegram"

    def __init__(self, secrets: Secrets, store, http: httpx.AsyncClient | None = None, long_poll_s: int = 25):
        self.secrets = secrets
        self.store = store
        self.http = http
        self.long_poll_s = long_poll_s
        self.pairing_until = 0.0
        self.paired: dict | None = None

    def configured(self) -> bool:
        return self.secrets.has("telegram", "bot_token")

    def public(self) -> dict:
        return {"has_token": self.configured(), "bot_username": self.store.get("telegram_bot_username", "")}

    def _url(self, method: str) -> str:
        return f"{API}/bot{self.secrets.get('telegram')['bot_token']}/{method}"

    def _c(self) -> httpx.AsyncClient:
        return self.http or httpx.AsyncClient(timeout=self.long_poll_s + 15)

    async def _call(self, method: str, **params):
        c = self._c()
        try:
            r = await c.post(self._url(method), json=params)
        except httpx.HTTPError as exc:
            raise ChannelError(f"Can't reach Telegram ({type(exc).__name__}).")
        finally:
            if c is not self.http:
                await c.aclose()
        if r.status_code == 401:
            raise ChannelError("Telegram rejected the bot token.", reauth=True)
        data = r.json() if r.content else {}
        if not data.get("ok"):
            raise ChannelError(data.get("description") or f"Telegram error {r.status_code}")
        return data["result"]

    async def test(self) -> str:
        if not self.configured():
            raise ChannelError("Paste the bot token first.")
        me = await self._call("getMe")
        self.store.set("telegram_bot_username", me.get("username", ""))
        return f"Connected as @{me.get('username')}."

    def start_pairing(self, seconds: int = 300) -> None:
        self.pairing_until = time.time() + seconds
        self.paired = None

    def pairing_state(self) -> dict:
        return {"active": time.time() < self.pairing_until and self.paired is None,
                "seconds_left": max(0, int(self.pairing_until - time.time())), "captured": self.paired}

    async def _photo(self, file_id: str) -> bytes | None:
        f = await self._call("getFile", file_id=file_id)
        if f.get("file_size", 0) > MAX_PHOTO:
            return None
        c = self._c()
        try:
            r = await c.get(f"{API}/file/bot{self.secrets.get('telegram')['bot_token']}/{f['file_path']}")
            r.raise_for_status()
            return r.content
        finally:
            if c is not self.http:
                await c.aclose()

    async def poll(self) -> list[InboundMessage]:
        if not self.configured():
            return []
        offset = int(self.store.get("telegram_offset", "0") or 0)
        updates = await self._call("getUpdates", offset=offset, timeout=self.long_poll_s,
                                   allowed_updates=["message", "callback_query"])
        out: list[InboundMessage] = []
        for u in updates:
            # The offset is committed after the pipeline has handled these (commit()); if we
            # crash first, Telegram resends them and the external_id table stops a repeat print.
            self._pending_offset = max(getattr(self, "_pending_offset", 0), u["update_id"] + 1)
            cq = u.get("callback_query")
            if cq and "from" in cq and cq.get("message"):  # a tap on one of the bot's buttons
                frm = cq["from"]
                name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or frm.get("username", "")
                out.append(InboundMessage(
                    channel="telegram", sender_id=str(frm["id"]), sender_name=name, body="",
                    external_id=f"telegram:{u['update_id']}", received_at=time.time(), reply=cq["message"]["chat"]["id"],
                    callback={"id": cq["id"], "data": cq.get("data") or "", "message_id": cq["message"]["message_id"]}))
                continue
            m = u.get("message")
            if not m or "from" not in m or m["from"].get("is_bot"):
                continue
            frm = m["from"]
            name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or frm.get("username", "")
            if time.time() < self.pairing_until and self.paired is None:
                self.paired = {"user_id": str(frm["id"]), "name": name}
                await self._send(m["chat"]["id"], "Paired with Wall Printer. Confirm in the app to start printing.")
                continue
            atts = []
            if m.get("photo"):
                best = max(m["photo"], key=lambda p: p.get("file_size", 0) if p.get("file_size", 0) <= MAX_PHOTO else 0)
                try:
                    data = await self._photo(best["file_id"])
                    if data:
                        atts.append(Attachment("photo.jpg", "image/jpeg", data))
                except ChannelError:
                    pass
            text = m.get("text") or m.get("caption") or ""
            if not text and not atts:
                continue
            out.append(InboundMessage(
                channel="telegram", sender_id=str(frm["id"]), sender_name=name, body=text.strip(),
                external_id=f"telegram:{u['update_id']}", received_at=float(m.get("date", time.time())),
                attachments=atts, reply=m["chat"]["id"]))
        return out

    def commit(self) -> None:
        if getattr(self, "_pending_offset", 0):
            self.store.set("telegram_offset", str(self._pending_offset))

    async def _send(self, chat_id, text: str) -> None:
        try:
            await self._call("sendMessage", chat_id=chat_id, text=text)
        except ChannelError:
            pass

    # ---------------------------------------------- bot replies (remote/bot.py) --
    @staticmethod
    def _markup(buttons):
        if buttons is None:
            return None
        return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}

    @staticmethod
    def _body(text: str, code: bool) -> dict:
        if not code:
            return {"text": text[:4000]}
        import html
        return {"text": f"<pre>{html.escape(text[:3900])}</pre>", "parse_mode": "HTML"}

    async def send(self, chat_id, text: str, buttons=None, code: bool = False) -> int | None:
        """Send a message (optionally with buttons, or as a block that copies with one tap)."""
        params = {"chat_id": chat_id, **self._body(text, code)}
        if buttons is not None:
            params["reply_markup"] = self._markup(buttons)
        try:
            return (await self._call("sendMessage", **params)).get("message_id")
        except ChannelError:
            return None

    async def edit(self, chat_id, message_id, text: str, buttons=None) -> None:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000]}
        params["reply_markup"] = self._markup(buttons) or {"inline_keyboard": []}
        try:
            await self._call("editMessageText", **params)
        except ChannelError:
            pass  # "message is not modified" and the like

    async def answer(self, callback_id: str, text: str = "") -> None:
        try:
            await self._call("answerCallbackQuery", callback_query_id=callback_id, text=text[:180])
        except ChannelError:
            pass

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        """The "/" menu in Telegram."""
        await self._call("setMyCommands", commands=[{"command": c, "description": d[:256] or c} for c, d in commands])

    async def ack(self, msg: InboundMessage, text: str) -> None:
        if msg.reply is not None:
            await self._send(msg.reply, text)
