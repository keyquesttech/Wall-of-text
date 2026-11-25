"""Mock adapter: reads JSON files from <data_dir>/mock-inbox/ (one message per file)
so the whole pipeline is testable with no accounts (BUILD_PLAN 9.2)."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from .base import Attachment, InboundMessage


def from_dict(d: dict) -> InboundMessage:
    atts = [Attachment(a.get("filename", "image"), a.get("content_type", "image/png"), base64.b64decode(a["data"]))
            for a in d.get("attachments", [])]
    return InboundMessage(
        channel=d.get("channel", "mock"), sender_id=str(d["sender_id"]), sender_name=d.get("sender_name", ""),
        body=d.get("body", ""), external_id=d.get("external_id") or f"mock:{time.time_ns()}",
        received_at=d.get("received_at", time.time()), subject=d.get("subject"), attachments=atts,
        authenticated=d.get("authenticated", True), reply=d.get("reply", "mock-chat"), callback=d.get("callback"))


class MockAdapter:
    id = "mock"
    label = "Test inbox"

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.acks: list[str] = []

    def configured(self) -> bool:
        return True

    def public(self) -> dict:
        return {"folder": str(self.folder)}

    async def poll(self) -> list[InboundMessage]:
        if not self.folder.exists():
            return []
        out = []
        for f in sorted(self.folder.glob("*.json")):
            try:
                out.append(from_dict(json.loads(f.read_text())))
            except (ValueError, KeyError):
                pass
            f.unlink(missing_ok=True)
        return out

    async def test(self) -> str:
        return "Mock inbox ready."

    async def ack(self, msg, text: str) -> None:
        self.acks.append(text)

    # the same bot replies as Telegram, recorded for tests and the dev page
    sent: list = []
    menu: list = []

    async def send(self, chat_id, text: str, buttons=None, code: bool = False) -> int:
        self.sent = self.sent + [{"chat": chat_id, "text": text, "buttons": buttons, "code": code}]
        return len(self.sent)

    async def edit(self, chat_id, message_id, text: str, buttons=None) -> None:
        self.sent = self.sent + [{"chat": chat_id, "edit": message_id, "text": text, "buttons": buttons}]

    async def answer(self, callback_id: str, text: str = "") -> None:
        pass

    async def set_commands(self, commands) -> None:
        self.menu = list(commands)
