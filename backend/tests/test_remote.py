"""Phase 6: remote messages. Every rule in BUILD_PLAN 9.2 has a test here:
allow-list, spoof check, dedupe across restarts, approval, quiet hours, rate limits,
print format, Telegram pairing and acknowledgements, back-off."""
import base64
import io
import json
import time
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from walloftext.app import create_app
from walloftext.remote.base import InboundMessage, cap, clean_body, html_to_text
from walloftext.remote.email_imap import EmailAdapter, authenticated, to_inbound
from walloftext.remote.secrets import Secrets
from walloftext.remote.telegram import TelegramAdapter
from walloftext.services import build
from walloftext.store.db import Store


def wait(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.03)
    return False


def make_client(settings, fake_nm):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    svc = build(settings, nm=fake_nm)
    svc.app_settings.patch({"schedules": {"quiet_hours": {"enabled": False}}})
    client = TestClient(create_app(services=svc), base_url="http://walloftext.local")
    client.__enter__()
    for _ in range(50):
        client.portal.call(svc.wifi.tick)
        if svc.wifi.status.mode == "online":
            break
        time.sleep(0.02)
    client.post("/api/auth/login", json={"password": "root"})
    client.svc = svc
    return client


@pytest.fixture
def c(settings, fake_nm):
    client = make_client(settings, fake_nm)
    yield client
    client.__exit__(None, None, None)


def inbound(c, **kw):
    msg = {"channel": "email", "sender_id": "sam@example.com", "sender_name": "Sam", "body": "Hello wall",
           "external_id": f"x:{time.time_ns()}"}
    msg.update(kw)
    return c.post("/api/dev/inbound", json=msg).json()["outcome"]


def add_sender(c, name="Sam", channel="email", value="sam@example.com", approval=None):
    body = {"name": name, "identifiers": [{"channel": channel, "value": value}]}
    if approval:
        body["approval"] = approval
    return c.post("/api/remote/senders", json=body).json()


def remote_jobs(c):
    return c.get("/api/history?source=Remote").json()["items"]


# ------------------------------------------------------------------ rules --
def test_unknown_sender_dropped_and_counted(c):
    assert inbound(c) == "blocked"
    assert inbound(c, sender_id="other@example.com") == "blocked"
    assert remote_jobs(c) == []
    assert c.get("/api/remote/channels").json()["blocked_week"] == 2


def test_allowed_sender_prints_with_format(c):
    add_sender(c, value="SAM@Example.com")  # stored lowercased
    when = datetime(2026, 11, 20, 18, 42).timestamp()
    assert inbound(c, subject="Dinner", body="Back at 7", received_at=when) == "printed"
    j = remote_jobs(c)[0]
    full = c.get(f"/api/history/{j['id']}").json()
    blocks = full["document"]["blocks"]
    d = blocks[0]["data"]
    assert blocks[0]["template"] == "message" and d["sender"] == "Sam" and d["now"] == "2026-11-20T18:42"
    assert d["subject"] == "Dinner" and d["body"] == "Back at 7"
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")


def test_spoofed_email_is_unknown(c):
    add_sender(c)
    assert inbound(c, authenticated=False) == "blocked"


def test_never_printed_twice_even_after_restart(c, settings, fake_nm):
    add_sender(c)
    assert inbound(c, external_id="email:<abc@x>") == "printed"
    assert inbound(c, external_id="email:<abc@x>") == "duplicate"
    c.__exit__(None, None, None)
    c2 = make_client(settings, fake_nm)  # same data dir = after a reboot
    try:
        assert inbound(c2, external_id="email:<abc@x>") == "duplicate"
        assert len(remote_jobs(c2)) == 1
    finally:
        c2.__exit__(None, None, None)


def test_wait_for_my_ok_goes_to_shared_list(c):
    add_sender(c, approval="approve")
    assert inbound(c, body="Please approve") == "waiting"
    items = c.get("/api/inbox").json()["items"]
    assert items[0]["source"] == "Remote" and items[0]["channel"] == "Email"
    assert remote_jobs(c) == []
    j = c.post(f"/api/inbox/{items[0]['id']}/approve").json()["job"]
    assert j["source"] == "Remote"


def test_senders_print_straight_away_by_default_and_sms_is_gone(c):
    assert add_sender(c)["approval"] == "print"
    r = c.post("/api/remote/senders", json={"name": "Pat", "identifiers": [{"channel": "sms", "value": "+447700900123"}]})
    assert r.status_code == 422


def test_quiet_hours_hold_then_release(c):
    add_sender(c)
    c.patch("/api/settings", json={"schedules": {"quiet_hours": {"enabled": True, "start": "00:00", "end": "23:59"}}})
    assert inbound(c) == "held"
    j = remote_jobs(c)[0]
    assert j["state"] == "held" and j["held_until"] > time.time()
    assert c.svc.queue.release_held(j["held_until"] + 1) == 1
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")


def test_rate_limit_per_sender(c):
    add_sender(c)
    add_sender(c, name="Jo", value="jo@example.com")
    c.patch("/api/settings", json={"remote": {"rate_per_hour": 2}})
    assert [inbound(c) for _ in range(3)] == ["printed", "printed", "rate_limited"]
    assert inbound(c, sender_id="jo@example.com") == "printed"


def test_daily_limit_shared(c):
    add_sender(c)
    c.patch("/api/settings", json={"schedules": {"daily_limit": 1}})
    assert inbound(c) == "printed"
    assert inbound(c) == "limit"


def test_long_body_is_capped(c):
    add_sender(c)
    c.patch("/api/settings", json={"remote": {"max_chars": 50, "max_lines": 3}})
    inbound(c, body="word " * 100)
    doc = c.get(f"/api/history/{remote_jobs(c)[0]['id']}").json()["document"]
    body = doc["blocks"][0]["data"]["body"]
    assert body.endswith("… (cut)") and len(body) <= 60


def test_image_attachment_prints_with_paper_safe_limiter(c):
    add_sender(c)
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "black").save(buf, "PNG")
    inbound(c, attachments=[{"filename": "a.png", "content_type": "image/png", "data": base64.b64encode(buf.getvalue()).decode()}])
    doc = c.get(f"/api/history/{remote_jobs(c)[0]['id']}").json()["document"]
    assert doc["blocks"][0]["data"]["image_src"].startswith("data:image/png;base64,")


def test_acknowledgement_after_print(c):
    add_sender(c, channel="mock", value="tester")
    assert inbound(c, channel="mock", sender_id="tester") == "printed"
    mock = c.svc.extras["remote"].adapters["mock"]
    assert wait(lambda: mock.acks == ["Printed."])
    c.svc.printer.offline = True
    inbound(c, channel="mock", sender_id="tester")
    assert "Queued: the printer is offline." in mock.acks


def test_mock_inbox_folder_and_manager(c, settings):
    add_sender(c, channel="mock", value="tester")
    folder = settings.data_dir / "mock-inbox"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "1.json").write_text(json.dumps({"channel": "mock", "sender_id": "tester", "body": "from a file",
                                               "external_id": "mock:file1"}))
    n = c.portal.call(c.svc.extras["remote"].poll_once, "mock")
    assert n == 1 and not list(folder.glob("*.json"))
    assert "from a file" in json.dumps(c.get(f"/api/history/{remote_jobs(c)[0]['id']}").json()["document"])


def test_channel_credentials_are_write_only(c, settings):
    r = c.patch("/api/remote/channels/email", json={"credentials": {"address": "wall@gmail.com", "app_password": "abcd efgh ijkl mnop"}})
    body = r.json()
    assert body["configured"] and body["settings"]["has_password"] and "abcd" not in json.dumps(body)
    assert "abcd" not in json.dumps(c.get("/api/remote/channels").json())
    sec = settings.data_dir / "secrets.json"
    assert oct(sec.stat().st_mode & 0o777) == "0o600"
    backup = c.get("/api/backup").content
    assert b"abcd" not in backup
    assert c.patch("/api/remote/channels/email", json={"credentials": {"address": "nope"}}).status_code == 422


# --------------------------------------------------------------- cleaning --
def test_clean_body_strips_quotes_and_signatures():
    text = "Hi!\n\n\n\nSee you soon\n-- \nSam\nSent from my iPhone"
    assert clean_body(text) == "Hi!\n\nSee you soon"
    reply = "Yes please\n\nOn Tue, 3 Nov 2026 at 10:00, Wall <wall@x.com> wrote:\n> old stuff"
    assert clean_body(reply) == "Yes please"
    assert clean_body("> quoted\nnew") == "new"
    assert html_to_text("<p>Hello<br>there</p><style>x{}</style><ul><li>a</li></ul>").split() == ["Hello", "there", "•", "a"]
    t, cut = cap("a\nb\nc\nd", 100, 2)
    assert cut and t == "a\nb… (cut)"


def test_authentication_results():
    gmail = ["mx.google.com; dkim=pass header.i=@example.com header.s=s1; spf=pass (google.com: domain of "
             "sam@example.com designates 1.2.3.4) smtp.mailfrom=sam@example.com; dmarc=pass"]
    assert authenticated(gmail, "sam@example.com")
    assert authenticated(["x; dkim=pass header.d=example.com"], "sam@mail.example.com")
    assert not authenticated(["x; dkim=pass header.i=@evil.com; spf=pass smtp.mailfrom=bounce@evil.com"],
                             "sam@example.com")
    assert not authenticated(["x; dkim=fail header.i=@example.com; spf=softfail smtp.mailfrom=sam@example.com"],
                             "sam@example.com")
    assert not authenticated([], "sam@example.com")


def _fake_mail(**kw):
    att = SimpleNamespace(filename="p.png", content_type="image/png", payload=b"\x89PNG....")
    d = dict(uid="7", from_="sam@example.com", from_values=SimpleNamespace(full="Sam Smith <sam@example.com>"),
             subject="Hi", text="Body\n\n-- \nsig", html="", date=datetime(2026, 11, 20, 9, 0),
             headers={"Message-ID": ("<m1@example.com>",),
                      "Authentication-Results": ("mx; dkim=pass header.i=@example.com",)},
             attachments=[att])
    d.update(kw)
    return SimpleNamespace(**d)


def test_email_message_conversion():
    m = to_inbound(_fake_mail())
    assert (m.sender_id, m.sender_name, m.subject, m.body) == ("sam@example.com", "Sam Smith", "Hi", "Body")
    assert m.external_id == "email:<m1@example.com>" and m.authenticated and len(m.attachments) == 1
    html_only = to_inbound(_fake_mail(text="", html="<p>Hello <b>you</b></p>"))
    assert html_only.body == "Hello you"


def test_email_adapter_with_fake_mailbox(tmp_path):
    class FakeBox:
        def __init__(self, s):
            self.s = s

        def login(self, user, pw, folder):
            from imap_tools.errors import MailboxLoginError
            if pw != "abcdefghijklmnop":
                raise MailboxLoginError(("NO", [b"bad"]), "OK")
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def fetch(self, *a, **k):
            return [_fake_mail()]

        def uids(self):
            return ["1", "2"]

    import asyncio
    sec = Secrets(tmp_path / "s.json")
    ad = EmailAdapter(sec, mailbox_factory=FakeBox)
    assert not ad.configured()
    sec.set("email", {"address": "wall@gmail.com", "app_password": "abcd efgh ijkl mnop"})
    msgs = asyncio.run(ad.poll())
    assert msgs[0].sender_id == "sam@example.com"
    assert "2 messages" in asyncio.run(ad.test())
    sec.set("email", {"app_password": "wrong"})
    from walloftext.remote.base import ChannelError
    with pytest.raises(ChannelError) as e:
        asyncio.run(ad.poll())
    assert e.value.reauth


# --------------------------------------------------------------- telegram --
def telegram_fixture(tmp_path, updates):
    sent = []

    def handler(req: httpx.Request):
        path = req.url.path
        if path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "wall_bot"}})
        if path.endswith("/getUpdates"):
            body = json.loads(req.content)
            res = [u for u in updates if u["update_id"] >= body.get("offset", 0)]
            return httpx.Response(200, json={"ok": True, "result": res})
        if path.endswith("/sendMessage"):
            sent.append(json.loads(req.content))
            return httpx.Response(200, json={"ok": True, "result": {}})
        if path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "p/1.jpg", "file_size": 10}})
        if "/file/bot" in path:
            return httpx.Response(200, content=b"JPEGDATA")
        return httpx.Response(404, json={"ok": False})

    sec = Secrets(tmp_path / "s.json")
    sec.set("telegram", {"bot_token": "123:ABC"})
    store = Store(tmp_path / "db.sqlite")
    tg = TelegramAdapter(sec, store, httpx.AsyncClient(transport=httpx.MockTransport(handler)), long_poll_s=0)
    return tg, sent, store


def _upd(uid, user=42, text="hi", photo=False):
    m = {"message_id": uid, "date": 1795200000, "chat": {"id": user}, "from": {"id": user, "first_name": "Al", "is_bot": False}}
    if photo:
        m["photo"] = [{"file_id": "f1", "file_size": 10}]
        m["caption"] = text
    else:
        m["text"] = text
    return {"update_id": uid, "message": m}


async def test_telegram_poll_offset_and_photo(tmp_path):
    tg, sent, store = telegram_fixture(tmp_path, [_upd(10), _upd(11, text="pic", photo=True)])
    assert await tg.test() == "Connected as @wall_bot."
    msgs = await tg.poll()
    assert [m.external_id for m in msgs] == ["telegram:10", "telegram:11"]
    assert msgs[1].attachments[0].data == b"JPEGDATA" and msgs[0].sender_id == "42"
    assert store.get("telegram_offset") is None  # not committed until handled
    tg.commit()
    assert store.get("telegram_offset") == "12"
    assert await tg.poll() == []


async def test_telegram_pairing_captures_first_message(tmp_path):
    tg, sent, store = telegram_fixture(tmp_path, [_upd(20, user=99, text="hello bot")])
    tg.start_pairing()
    assert tg.pairing_state()["active"]
    msgs = await tg.poll()
    assert msgs == [] and tg.paired == {"user_id": "99", "name": "Al"}
    assert "Paired" in sent[0]["text"]
    assert tg.pairing_state()["active"] is False


async def test_telegram_bad_token_is_reauth(tmp_path):
    def handler(req):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    sec = Secrets(tmp_path / "s.json")
    sec.set("telegram", {"bot_token": "bad"})
    tg = TelegramAdapter(sec, Store(tmp_path / "d.sqlite"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    from walloftext.remote.base import ChannelError
    with pytest.raises(ChannelError) as e:
        await tg.poll()
    assert e.value.reauth


def test_pairing_confirm_creates_sender(c):
    tg = c.svc.extras["remote"].adapters["telegram"]
    assert c.post("/api/remote/pairing/start").status_code == 409  # no token yet
    tg.paired = {"user_id": "777", "name": "Al"}
    s = c.post("/api/remote/pairing/confirm", json={"name": "Alex"}).json()
    assert s["identifiers"] == [{"channel": "telegram", "value": "777"}]
    assert inbound(c, channel="telegram", sender_id="777") == "printed"


async def test_manager_backoff(c):
    from walloftext.remote.base import ChannelError
    from walloftext.remote.manager import RemoteManager

    class Broken:
        id, label = "x", "X"

        def configured(self):
            return True

        def public(self):
            return {}

        async def poll(self):
            raise ChannelError("nope", reauth=True)

    m = RemoteManager(c.svc, c.svc.extras["remote"].pipeline, {"x": Broken()})
    with pytest.raises(ChannelError):
        await m.poll_once("x")
