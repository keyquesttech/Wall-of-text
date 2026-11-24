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

# Only the Wi-Fi card is built in; everything else is made by saving a print with the bookmark
# button. A saved print may hold {{name}} placeholders, which become fill-in fields.
BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "b-wifi", "name": "Wi-Fi for guests", "icon": "wifi",
        "fields": [{"key": "ssid", "label": "Network name"}, {"key": "password", "label": "Password"}],
        "document": {"blocks": [{"type": "heading", "text": "Wi-Fi", "size": "XL"},
                                {"type": "qr", "data": "WIFI:T:WPA;S:{{ssid}};P:{{password}};;", "size": "M"},
                                {"type": "text", "text": "Network: {{ssid}}\nPassword: {{password}}", "align": "center"}]},
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


def placeholder_fields(doc: dict) -> list[dict]:
    """{{name}} placeholders in a saved print → fill-in fields, in the order they appear."""
    keys: list[str] = []
    for m in _FIELD.finditer(json.dumps(doc, ensure_ascii=False)):
        if m.group(1) not in keys:
            keys.append(m.group(1))
    return [{"key": k, "label": k.replace("_", " ").capitalize(), "multiline": False} for k in keys[:12]]


class Templates:
    def __init__(self, svc: "Services"):
        self.svc = svc

    def list(self) -> list[dict]:
        rows = self.svc.store.conn().execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
        user = []
        for r in rows:
            doc = json.loads(r["document"])
            user.append({"id": r["id"], "name": r["name"], "icon": r["icon"], "builtin": False,
                         "fields": placeholder_fields(doc), "document": doc})
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
        from datetime import datetime
        return {"blocks": [{"type": "slip", "template": "shopping",
                            "data": {"items": self.open_items(name), "now": datetime.now().isoformat(timespec="minutes")}}]}

    def publish(self, name: str) -> None:
        self.svc.events.publish("list", {"list": name})
