"""Remote-message primitives (BUILD_PLAN 9.2)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class InboundMessage:
    channel: str  # "email" | "telegram" | "sms" | "mock"
    sender_id: str  # email address (lowercase), Telegram numeric user id, phone number
    sender_name: str
    body: str
    external_id: str  # never printed twice
    received_at: float
    subject: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    authenticated: bool = True  # email: SPF/DKIM pass for the From domain
    reply: object = None  # adapter-specific handle for acknowledgements


class ChannelError(Exception):
    def __init__(self, message: str, reauth: bool = False):
        super().__init__(message)
        self.reauth = reauth


class Adapter(Protocol):
    id: str
    label: str

    def configured(self) -> bool: ...
    async def poll(self) -> list[InboundMessage]: ...
    async def test(self) -> str: ...
    async def ack(self, msg: InboundMessage, text: str) -> None: ...


# --------------------------------------------------------------- cleaning --

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "section", "table"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self.skip += 1
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("• ")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    p = _Text()
    try:
        p.feed(s)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", s)
    return html.unescape("".join(p.out))


SIG_MARKERS = (
    re.compile(r"^-- ?$"),
    re.compile(r"^sent from my ", re.I),
    re.compile(r"^get outlook for ", re.I),
    re.compile(r"^sent from (mail|yahoo|gmail|outlook) for ", re.I),
)
QUOTE_HEADERS = (
    re.compile(r"^on .{4,200} wrote:\s*$", re.I),
    re.compile(r"^-{2,}\s*original message\s*-{2,}", re.I),
    re.compile(r"^-{2,}\s*forwarded message\s*-{2,}", re.I),
    re.compile(r"^from: .+", re.I),
    re.compile(r"^le .{4,200} a écrit\s*:\s*$", re.I),
    re.compile(r"^am .{4,200} schrieb .+:\s*$", re.I),
)


def clean_body(text: str) -> str:
    """Strip quoted replies and signatures, collapse blank lines (BUILD_PLAN 9.2)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").split("\n")
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        if any(p.match(s.strip()) for p in SIG_MARKERS):
            break
        if any(p.match(s.strip()) for p in QUOTE_HEADERS) and out:
            break
        if s.lstrip().startswith(">"):
            continue
        out.append(s)
    text = "\n".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def cap(text: str, max_chars: int, max_lines: int) -> tuple[str, bool]:
    lines = text.split("\n")
    cut = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        cut = True
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] if " " in text[:max_chars] else text[:max_chars]
        cut = True
    if cut:
        text = text.rstrip() + "… (cut)"
    return text, cut
