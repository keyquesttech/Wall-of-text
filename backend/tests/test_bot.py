"""Telegram bot: commands, templates, per-chat settings, asking how to print, print styles (mock adapter)."""
import time

import pytest

from test_remote import add_sender, inbound, make_client, remote_jobs, wait


@pytest.fixture
def c(settings, fake_nm):
    client = make_client(settings, fake_nm)
    add_sender(client, channel="telegram", value="42")
    client.mock = client.svc.extras["remote"].adapters["mock"]
    yield client
    client.__exit__(None, None, None)


def tg(c, body="", **kw):
    return inbound(c, channel="telegram", sender_id="42", body=body, **kw)


def tap(c, data, message_id=1):
    return tg(c, callback={"id": "cb", "data": data, "message_id": message_id})


def last(c):
    return c.mock.sent[-1]


def doc_of(c, job):
    return c.get(f"/api/history/{job['id']}").json()["document"]


def test_help_lists_builtin_and_custom_commands(c):
    assert tg(c, "/help") == "command"
    text = last(c)["text"]
    assert "/settings" in text and "/templates" in text and "/weather" in text and "/big" in text
    assert remote_jobs(c) == []  # commands never print


def test_unknown_command_and_unknown_sender(c):
    tg(c, "/nope")
    assert "don't know /nope" in last(c)["text"]
    n = len(c.mock.sent)
    assert inbound(c, channel="telegram", sender_id="999", body="/help") == "blocked"
    assert len(c.mock.sent) == n  # strangers get no reply


def test_templates_come_back_copyable(c):
    c.patch("/api/settings", json={"telegram": {"templates": [{"name": "Shopping", "text": "Shopping:\n- \n- "}]}})
    tg(c, "/templates")
    assert last(c)["buttons"] == [[("Shopping", "tpl:0")]]
    tap(c, "tpl:0")
    sent = c.mock.sent[-2]
    assert sent["text"] == "Shopping:\n- \n- " and sent["code"] is True


def test_custom_reply_action_and_style_commands(c):
    c.patch("/api/settings", json={"telegram": {"commands": [
        {"name": "wifi", "description": "Wi-Fi password", "type": "reply", "text": "hunter2", "copyable": True},
        {"name": "fortune", "type": "action", "action": "random_fortune"},
        {"name": "big", "type": "style", "style": "big", "size": "XL"},
        {"name": "Bad Name!", "type": "reply", "text": "x"},
        {"name": "help", "type": "reply", "text": "can't override a built-in"}]}})
    tg(c, "/wifi")
    assert last(c) == {"chat": "mock-chat", "text": "hunter2", "buttons": None, "code": True}
    tg(c, "/fortune")
    assert "fortune" in last(c)["text"].lower()
    tg(c, "/big")
    assert "next message prints as big text" in last(c)["text"]
    assert tg(c, "Back at 7") == "printed"
    blocks = doc_of(c, remote_jobs(c)[0])["blocks"]
    assert any(b["type"] == "heading" and b["text"] == "Back at 7" and b["size"] == "XL" for b in blocks)
    assert tg(c, "Normal again") == "printed"  # the style was for one message only
    assert doc_of(c, remote_jobs(c)[0])["blocks"][0]["template"] == "message"
    assert tg(c, "/big Right now") == "printed"
    assert any(b.get("text") == "Right now" for b in doc_of(c, remote_jobs(c)[0])["blocks"])
    menu = c.svc.extras["remote"].pipeline.bot.menu()
    assert ("wifi", "Wi-Fi password") in menu and not any(m[0] == "bad name!" for m in menu)


def test_settings_buttons_change_how_my_messages_print(c):
    tg(c, "/settings")
    assert "Style: Message slip · Size: M" in last(c)["text"]
    tap(c, "set:style:checklist")
    tap(c, "set:size:L")
    assert "Style: Checklist · Size: L" in last(c)["text"] and "edit" in last(c)
    assert tg(c, "- milk\n- eggs\nbread") == "printed"
    cl = [b for b in doc_of(c, remote_jobs(c)[0])["blocks"] if b["type"] == "checklist"][0]
    assert [i["text"] for i in cl["items"]] == ["milk", "eggs", "bread"] and cl["size"] == "L"


def test_ask_how_to_print_then_print(c):
    c.patch("/api/settings", json={"telegram": {"ask_options": True}})
    assert tg(c, "Dinner at 8") == "asking"
    prompt = last(c)
    assert "How should this print?" in prompt["text"]
    token = prompt["buttons"][2][0][1].split(":")[1]
    assert remote_jobs(c) == []
    tap(c, f"p:{token}:style:plain")
    tap(c, f"p:{token}:size:XL")
    assert "Plain text · Size: XL" in last(c)["text"]
    assert tap(c, f"p:{token}:go") == "printed"
    blocks = doc_of(c, remote_jobs(c)[0])["blocks"]
    assert blocks[-1] == {"type": "text", "text": "Dinner at 8", "size": "XL"}
    assert tap(c, f"p:{token}:go") == "command"  # tapping again does nothing
    assert "already been printed" in last(c)["text"]


def test_ask_cancel_and_timeouts(c):
    bot = c.svc.extras["remote"].pipeline.bot
    c.patch("/api/settings", json={"telegram": {"ask_options": True, "ask_timeout_s": 30, "on_timeout": "print"}})
    tg(c, "One")
    token = last(c)["buttons"][2][1][1].split(":")[1]
    tap(c, f"p:{token}:no")
    assert "Cancelled" in last(c)["text"] and remote_jobs(c) == []
    tg(c, "Two")
    pend = bot._pending()
    for v in pend.values():
        v["created"] -= 60
    bot._save("telegram_pending", pend)
    assert c.portal.call(bot.expire, c.mock) == 1
    assert "No answer, so printing" in last(c)["text"] and len(remote_jobs(c)) == 1
    c.patch("/api/settings", json={"telegram": {"on_timeout": "cancel"}})
    tg(c, "Three")
    pend = bot._pending()
    for v in pend.values():
        v["created"] -= 60
    bot._save("telegram_pending", pend)
    c.portal.call(bot.expire, c.mock)
    assert "wasn't printed" in last(c)["text"] and len(remote_jobs(c)) == 1
    tg(c, "Four")
    tg(c, "/cancel")
    assert "Cancelled" in last(c)["text"] and bot._pending() == {}


def test_slip_size_and_email_unchanged(c):
    add_sender(c, name="Ann", value="ann@example.com")
    assert inbound(c, sender_id="ann@example.com", body="Hi") == "printed"  # email: no bot, default slip
    d = doc_of(c, remote_jobs(c)[0])["blocks"][0]["data"]
    assert "size" not in d
    c.patch("/api/settings", json={"telegram": {"defaults": {"style": "message", "size": "L"}}})
    tg(c, "Bigger slip")
    assert doc_of(c, remote_jobs(c)[0])["blocks"][0]["data"]["size"] == "L"
    assert wait(lambda: all(j["state"] in ("done", "printing", "queued") for j in remote_jobs(c)))
