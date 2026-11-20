"""Email over IMAP with an app password (BUILD_PLAN 9.2).

Use a dedicated personal Gmail account with 2-Step Verification and an app
password (Workspace accounts need OAuth and are not supported). Any provider
that allows IMAP with an app password works too.

Spoofing: the sender only counts as authenticated when the receiving server's
Authentication-Results header shows spf=pass or dkim=pass for the From domain.
"""
from __future__ import annotations

import asyncio
import email.utils
import re
import time

from .base import Attachment, ChannelError, InboundMessage, clean_body, html_to_text
from .secrets import Secrets

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp", "image/heic")


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower().strip(">").strip()


def _aligned(found: str, from_domain: str) -> bool:
    found = found.lower().lstrip("@").strip(";").strip()
    if "@" in found:
        found = found.rsplit("@", 1)[1]
    return bool(found) and (from_domain == found or from_domain.endswith("." + found) or found.endswith("." + from_domain))


def authenticated(auth_results: list[str], from_addr: str) -> bool:
    """True if any Authentication-Results shows spf=pass or dkim=pass aligned with the From domain."""
    fd = _domain(from_addr)
    for header in auth_results:
        h = header.lower()
        for m in re.finditer(r"dkim=pass[^;]*?header\.(?:i|d)=([^\s;]+)", h):
            if _aligned(m.group(1), fd):
                return True
        for m in re.finditer(r"spf=pass[^;]*?smtp\.mailfrom=([^\s;]+)", h):
            if _aligned(m.group(1), fd):
                return True
    return False


def to_inbound(msg) -> InboundMessage:
    """imap_tools MailMessage → InboundMessage."""
    name, addr = email.utils.parseaddr(msg.from_values.full if getattr(msg, "from_values", None) else msg.from_)
    addr = (addr or msg.from_ or "").lower()
    headers = {k.lower(): v for k, v in (msg.headers or {}).items()}
    auth = list(headers.get("authentication-results", ()))
    body = msg.text or html_to_text(msg.html or "")
    mid = (headers.get("message-id", ("",))[0] or "").strip()
    atts = []
    for a in msg.attachments or []:
        if (a.content_type or "").lower() in IMAGE_TYPES and len(a.payload or b"") < 12 * 1024 * 1024:
            atts.append(Attachment(a.filename or "image", a.content_type, a.payload))
    return InboundMessage(
        channel="email", sender_id=addr, sender_name=name or addr, body=clean_body(body),
        external_id=f"email:{mid or msg.uid}", received_at=msg.date.timestamp() if msg.date else time.time(),
        subject=(msg.subject or "").strip() or None, attachments=atts[:1],
        authenticated=authenticated(auth, addr),
    )


class EmailAdapter:
    id = "email"
    label = "Email"

    def __init__(self, secrets: Secrets, mailbox_factory=None):
        self.secrets = secrets
        self.mailbox_factory = mailbox_factory  # tests inject a fake

    def configured(self) -> bool:
        return self.secrets.has("email", "address", "app_password")

    def public(self) -> dict:
        s = self.secrets.get("email")
        return {"address": s.get("address", ""), "imap_host": s.get("imap_host", "imap.gmail.com"),
                "has_password": bool(s.get("app_password"))}

    def _mailbox(self):
        s = self.secrets.get("email")
        if self.mailbox_factory:
            return self.mailbox_factory(s)
        from imap_tools import MailBox

        return MailBox(s.get("imap_host") or "imap.gmail.com", timeout=30)

    def _fetch(self) -> list[InboundMessage]:
        from imap_tools import AND
        from imap_tools.errors import MailboxLoginError

        s = self.secrets.get("email")
        try:
            with self._mailbox().login(s["address"], s["app_password"].replace(" ", ""), "INBOX") as mb:
                msgs = list(mb.fetch(AND(seen=False), mark_seen=True, bulk=20, limit=20))
        except MailboxLoginError:
            raise ChannelError("The mailbox refused the app password.", reauth=True)
        except ChannelError:
            raise
        except Exception as exc:
            raise ChannelError(f"Can't reach the mailbox ({type(exc).__name__}).")
        return [to_inbound(m) for m in msgs]

    async def poll(self) -> list[InboundMessage]:
        if not self.configured():
            return []
        return await asyncio.to_thread(self._fetch)

    async def test(self) -> str:
        def check():
            from imap_tools.errors import MailboxLoginError

            s = self.secrets.get("email")
            try:
                with self._mailbox().login(s["address"], s["app_password"].replace(" ", ""), "INBOX") as mb:
                    n = len(list(mb.uids()))
            except MailboxLoginError:
                raise ChannelError("The mailbox refused the app password.", reauth=True)
            except Exception as exc:
                raise ChannelError(f"Can't reach the mailbox ({type(exc).__name__}).")
            return f"Connected. {n} message{'s' if n != 1 else ''} in the inbox."

        if not self.configured():
            raise ChannelError("Add the address and app password first.")
        return await asyncio.to_thread(check)

    async def ack(self, msg: InboundMessage, text: str) -> None:
        return None  # email replies need SMTP; off in v1 (BUILD_PLAN 9.2)
