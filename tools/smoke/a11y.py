#!/usr/bin/env python3
"""axe-core accessibility check of every screen against the mock backend (Phase 8).

    tools/smoke/run_server.sh &   then   .venv/bin/python tools/smoke/a11y.py
Prints serious/critical violations; exits 1 if any.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8099"
AXE = (Path(__file__).resolve().parents[2] / "frontend/node_modules/axe-core/axe.min.js").read_text()
PAGES = ["/signin", "/setup", "/note", "/", "/create/draw", "/create/image", "/create/templates", "/create/list",
         "/schedules", "/history", "/settings", "/settings/printer", "/settings/fonts", "/settings/button",
         "/settings/schedules", "/settings/history", "/settings/weather", "/settings/calendars", "/settings/tasks",
         "/settings/remote", "/settings/access", "/settings/wifi", "/settings/device", "/settings/display"]
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844})
    for path in ("/signin", "/note"):  # signed out first
        pg.goto(B + path)
        pg.wait_for_timeout(500)
        pg.add_script_tag(content=AXE)
        res = pg.evaluate("async () => (await axe.run()).violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length}))")
        for v in res:
            print(f"{path:24s} (signed out) {v}")
        bad += sum(1 for v in res if v["impact"] in ("serious", "critical"))
    pg.goto(B + "/signin")
    pg.fill("#pw", "root")
    pg.click("#go")
    pg.wait_for_url(B + "/")
    for path in PAGES:
        pg.goto(B + path)
        pg.wait_for_timeout(700)
        pg.add_script_tag(content=AXE)
        res = pg.evaluate("""async () => (await axe.run(document, {resultTypes: ['violations']})).violations
            .map(v => ({id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0,3).map(n => n.target.join(' '))}))""")
        serious = [v for v in res if v["impact"] in ("serious", "critical")]
        bad += len(serious)
        for v in res:
            print(f"{path:24s} {v['impact']:9s} {v['id']}: {v['help']}  {v['nodes']}")
    b.close()
print("serious/critical:", bad)
sys.exit(1 if bad else 0)
