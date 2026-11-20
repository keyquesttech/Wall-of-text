"""Templates (built-in fill-ins + your own) and the shared shopping list (Phase 7)."""
from __future__ import annotations

import copy
import json
import re
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .services import Services

BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "b-note", "name": "Note to self", "icon": "note",
        "fields": [{"key": "text", "label": "Note", "multiline": True}],
        "document": {"blocks": [{"type": "datetime", "size": "S", "align": "left"},
                                {"type": "text", "text": "{{text}}", "size": "L"}]},
    },
    {
        "id": "b-big", "name": "Big message", "icon": "big",
        "fields": [{"key": "text", "label": "Message"}],
        "document": {"blocks": [{"type": "heading", "text": "{{text}}", "size": "XL", "font": "sans"}],
                     "options": {"border": True}},
    },
    {
        "id": "b-todo", "name": "To-do list", "icon": "list",
        "fields": [{"key": "title", "label": "Title"}, {"key": "items", "label": "One thing per line", "multiline": True, "list": True}],
        "document": {"blocks": [{"type": "heading", "text": "{{title}}", "size": "L", "align": "left"},
                                {"type": "checklist", "items": "{{items}}"}]},
        "defaults": {"title": "To do"},
    },
    {
        "id": "b-wifi", "name": "Wi-Fi for guests", "icon": "wifi",
        "fields": [{"key": "ssid", "label": "Network name"}, {"key": "password", "label": "Password"}],
        "document": {"blocks": [{"type": "heading", "text": "Wi-Fi", "size": "XL"},
                                {"type": "qr", "data": "WIFI:T:WPA;S:{{ssid}};P:{{password}};;", "size": "M"},
                                {"type": "text", "text": "Network: {{ssid}}\nPassword: {{password}}", "align": "center"}]},
    },
    {
        "id": "b-card", "name": "Greeting card", "icon": "card",
        "fields": [{"key": "to", "label": "To"}, {"key": "message", "label": "Message", "multiline": True},
                   {"key": "from", "label": "From"}],
        "document": {"blocks": [{"type": "sticker", "name": "heart"},
                                {"type": "heading", "text": "{{to}}", "size": "XL", "font": "sans"},
                                {"type": "divider", "style": "wave"},
                                {"type": "text", "text": "{{message}}", "size": "L", "align": "center"},
                                {"type": "text", "text": "— {{from}}", "size": "M", "align": "right"}],
                     "options": {"border": True}},
    },
    {
        "id": "b-recipe", "name": "Recipe card", "icon": "recipe",
        "fields": [{"key": "title", "label": "Dish"}, {"key": "ingredients", "label": "Ingredients (one per line)", "multiline": True, "list": True},
                   {"key": "steps", "label": "Method", "multiline": True}],
        "document": {"blocks": [{"type": "heading", "text": "{{title}}", "size": "L"},
                                {"type": "banner", "text": "Ingredients"},
                                {"type": "checklist", "items": "{{ingredients}}", "size": "S"},
                                {"type": "banner", "text": "Method"},
                                {"type": "text", "text": "{{steps}}", "size": "S"}]},
    },
    {
        "id": "b-chore", "name": "Chore chart", "icon": "chore",
        "fields": [{"key": "who", "label": "Who"}, {"key": "items", "label": "Chores (one per line)", "multiline": True, "list": True}],
        "document": {"blocks": [{"type": "banner", "text": "Chores for {{who}}"},
                                {"type": "columns", "left": "Mon Tue Wed Thu Fri", "right": "", "size": "S", "font": "mono"},
                                {"type": "checklist", "items": "{{items}}"}]},
    },
    {
        "id": "b-sticker", "name": "Sticker", "icon": "sticker",
        "fields": [{"key": "caption", "label": "Caption (optional)"}],
        "document": {"blocks": [{"type": "sticker", "name": "star", "size": "L"},
                                {"type": "text", "text": "{{caption}}", "size": "L", "align": "center"}]},
    },
]

_FIELD = re.compile(r"\{\{(\w+)\}\}")


def fill(template: dict, values: dict[str, str]) -> dict:
    """Replace {{field}} placeholders. A whole-string list field becomes checklist items."""
    vals = {**template.get("defaults", {}), **{k: v for k, v in values.items() if isinstance(v, str)}}
    list_fields = {f["key"] for f in template.get("fields", []) if f.get("list")}

    def sub(v: Any) -> Any:
        if isinstance(v, str):
            m = _FIELD.fullmatch(v)
            if m and m.group(1) in list_fields:
                return [{"text": line.strip()} for line in vals.get(m.group(1), "").splitlines() if line.strip()]
            return _FIELD.sub(lambda mm: vals.get(mm.group(1), ""), v)
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v

    doc = sub(copy.deepcopy(template["document"]))
    # drop blocks that ended up empty (e.g. an optional caption)
    doc["blocks"] = [b for b in doc["blocks"] if not (b.get("type") in ("text", "heading") and not b.get("text", "").strip(" —-"))
                     and not (b.get("type") == "checklist" and not b.get("items"))]
    return doc


class Templates:
    def __init__(self, svc: "Services"):
        self.svc = svc

    def list(self) -> list[dict]:
        rows = self.svc.store.conn().execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
        user = [{"id": r["id"], "name": r["name"], "icon": r["icon"], "builtin": False, "fields": [],
                 "document": json.loads(r["document"])} for r in rows]
        return [{**t, "builtin": True} for t in BUILTIN_TEMPLATES] + user

    def get(self, tid: str) -> dict | None:
        return next((t for t in self.list() if t["id"] == tid), None)

    def add(self, name: str, document: dict, icon: str | None = None) -> dict:
        tid = "u-" + uuid.uuid4().hex[:8]
        self.svc.store.conn().execute("INSERT INTO templates(id,name,icon,document,created_at) VALUES(?,?,?,?,?)",
                                      (tid, name[:60], icon, json.dumps(document), time.time()))
        return self.get(tid)

    def delete(self, tid: str) -> bool:
        return self.svc.store.conn().execute("DELETE FROM templates WHERE id=?", (tid,)).rowcount > 0


class Lists:
    def __init__(self, svc: "Services"):
        self.svc = svc

    def items(self, name: str = "shopping") -> list[dict]:
        rows = self.svc.store.conn().execute(
            "SELECT * FROM list_items WHERE list=? ORDER BY done, position, id", (name,)).fetchall()
        return [{**dict(r), "done": bool(r["done"])} for r in rows]

    def open_items(self, name: str = "shopping") -> list[str]:
        return [i["text"] for i in self.items(name) if not i["done"]]

    def add(self, name: str, text: str, by: str | None = None) -> dict:
        c = self.svc.store.conn()
        pos = c.execute("SELECT COALESCE(MAX(position),0)+1 FROM list_items WHERE list=?", (name,)).fetchone()[0]
        cur = c.execute("INSERT INTO list_items(list,text,done,position,added_by,created_at) VALUES(?,?,0,?,?,?)",
                        (name, text.strip()[:120], pos, by, time.time()))
        self.publish(name)
        return dict(c.execute("SELECT * FROM list_items WHERE id=?", (cur.lastrowid,)).fetchone())

    def update(self, iid: int, done: bool | None = None, text: str | None = None) -> bool:
        c = self.svc.store.conn()
        row = c.execute("SELECT list FROM list_items WHERE id=?", (iid,)).fetchone()
        if not row:
            return False
        if done is not None:
            c.execute("UPDATE list_items SET done=?, done_at=? WHERE id=?", (1 if done else 0, time.time() if done else None, iid))
        if text is not None and text.strip():
            c.execute("UPDATE list_items SET text=? WHERE id=?", (text.strip()[:120], iid))
        self.publish(row[0])
        return True

    def delete(self, iid: int) -> bool:
        c = self.svc.store.conn()
        row = c.execute("SELECT list FROM list_items WHERE id=?", (iid,)).fetchone()
        n = c.execute("DELETE FROM list_items WHERE id=?", (iid,)).rowcount
        if row:
            self.publish(row[0])
        return n > 0

    def clear_done(self, name: str = "shopping") -> int:
        n = self.svc.store.conn().execute("DELETE FROM list_items WHERE list=? AND done=1", (name,)).rowcount
        self.publish(name)
        return n

    def document(self, name: str = "shopping") -> dict:
        items = self.open_items(name)
        return {"blocks": [{"type": "heading", "text": name.capitalize(), "size": "L", "align": "left"},
                           {"type": "datetime", "format": "%a %-d %b", "size": "S", "align": "left"},
                           {"type": "checklist", "items": [{"text": i} for i in items]} if items else
                           {"type": "text", "text": "Nothing on the list.", "size": "M"}]}

    def publish(self, name: str) -> None:
        self.svc.events.publish("list", {"list": name})
