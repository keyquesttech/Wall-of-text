#!/usr/bin/env python3
"""Playwright smoke test against a mock backend (BUILD_PLAN 12: 390x844 and 1200x800).

    tools/smoke/run_server.sh &          # mock backend on :8099
    .venv/bin/python tools/smoke/smoke.py [--shots DIR]

Exits non-zero on the first failed check. Screenshots go to --shots.
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://localhost:8099")
ap.add_argument("--shots", default="/tmp/wot-shots")
ap.add_argument("--only", default="")
args = ap.parse_args()
shots = Path(args.shots)
shots.mkdir(parents=True, exist_ok=True)
errors: list[str] = []


def shot(page, name):
    page.screenshot(path=str(shots / f"{name}.png"), full_page=False)


def sign_in(page):
    page.goto(args.base + "/")
    page.wait_for_url("**/signin**")
    page.fill("#pw", "nope")
    page.click("#go")
    expect(page.locator("#msg")).to_contain_text("isn't right")
    page.fill("#pw", "root")
    page.click("#go")
    page.wait_for_url(args.base + "/")


def run(viewport, tag):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=viewport, device_scale_factor=2 if viewport["width"] < 500 else 1)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"{tag}: {e}"))
        page.on("console", lambda m: m.type == "error" and "401" not in m.text and errors.append(f"{tag} console: {m.text}"))
        sign_in(page)
        # quiet hours (22:00-07:30 by default) would hold the remote message: run the same at any hour
        page.request.patch(args.base + "/api/settings", data={"schedules": {"quiet_hours": {"enabled": False}}})
        wide = viewport["width"] >= 1024
        def as_printed():
            if not wide:
                page.click("button:has-text('As printed')")
            expect(page.locator(".receipt.img img").first).to_be_visible(timeout=10000)
        def edit_view():
            if not wide:
                page.click(".seg button:has-text('Edit')")
        def printed_toast():
            expect(page.locator(".toastf")).to_contain_text("Printed", timeout=15000)
        shot(page, f"{tag}-01-create-empty")
        page.fill("#ttl", "Shopping")
        page.fill("#note", "☐ Buy milk\n---\nand call Grandma at six")
        page.wait_for_timeout(600)
        shot(page, f"{tag}-02-create-typed")
        as_printed()
        page.wait_for_timeout(400)
        shot(page, f"{tag}-02b-as-printed")
        edit_view()
        page.click("button.btn-print")
        page.wait_for_timeout(500)
        shot(page, f"{tag}-03-printing")
        printed_toast()
        shot(page, f"{tag}-04-printed")
        page.click(".pill")
        expect(page.locator(".sheetf")).to_be_visible()
        shot(page, f"{tag}-05-status")
        page.keyboard.press("Escape")
        for name, path in [("history", "/history"), ("schedules", "/schedules"), ("settings", "/settings"),
                           ("wifi", "/settings/wifi"), ("access", "/settings/access")]:
            if args.only and name not in args.only.split(","):
                continue
            page.goto(args.base + path)
            page.wait_for_timeout(600)
            shot(page, f"{tag}-10-{name}")
        page.goto(args.base + "/history")
        page.locator("a.hcard").first.click()
        expect(page.locator(".sheetf .receipt img")).to_be_visible()
        page.wait_for_timeout(400)
        shot(page, f"{tag}-11-history-detail")
        page.keyboard.press("Escape")
        page.request.post(args.base + "/api/dev/net-state", data={"printer_offline": True})
        page.goto(args.base + "/")
        expect(page.locator(".banner")).to_contain_text("offline", timeout=8000)
        expect(page.locator("button:has-text('Add to queue')")).to_be_visible()
        shot(page, f"{tag}-12-offline-banner")
        page.request.post(args.base + "/api/dev/net-state", data={"printer_offline": False})
        # Schedules: New opens the editor (like "Start from Morning briefing")
        page.goto(args.base + "/schedules")
        page.click("button.btn-pink:has-text('New')")
        page.wait_for_url("**/schedules/new")
        page.click(".chip:has-text('Fortune')")
        expect(page.locator("#sname")).to_have_value("Daily fortune")
        page.click(".chip:has-text('Weekdays')")
        expect(page.locator(".receipt.img img")).to_be_visible(timeout=10000)
        shot(page, f"{tag}-19-new-schedule")
        page.click("button.btn-pink:has-text('Save schedule')")
        expect(page.locator(".toastf")).to_contain_text("Scheduled for")
        page.wait_for_url(args.base + "/schedules")
        # Create's Schedule button: just this message
        page.goto(args.base + "/")
        page.fill("#note", "Bins out tonight")
        page.click("button.btn-sched")
        expect(page.locator(".sheetf h2")).to_have_text("Schedule this message")
        page.click(".sheetf button:has-text('Tomorrow')")
        page.click(".sheetf button.btn-pink:has-text('Save schedule')")
        expect(page.locator(".toastf")).to_contain_text("Scheduled for tomorrow")
        page.goto(args.base + "/schedules")
        page.locator(".scard button.row:has-text('Daily fortune')").first.click()  # by name: order depends on the hour
        page.wait_for_url("**/schedules/*")
        expect(page.locator("#sname")).to_have_value("Daily fortune")
        expect(page.locator(".receipt.img img")).to_be_visible(timeout=10000)
        page.wait_for_timeout(300)
        shot(page, f"{tag}-20-routine")
        page.click("button.btn-pink:has-text('Save schedule')")
        page.wait_for_url(args.base + "/schedules")
        page.wait_for_timeout(400)
        shot(page, f"{tag}-21-schedules")
        # every settings page renders without errors
        for sp in ["printer", "paper", "fonts", "history", "weather", "google", "fortunes", "inbox", "guest", "email", "telegram",
                   "schedules", "time", "button", "light", "fan", "strip", "wifi", "access", "backup", "device", "display"]:
            page.goto(args.base + "/settings/" + sp)
            expect(page.locator("h1")).not_to_have_text("Settings")  # a real page, not the index
            page.wait_for_timeout(250)
            if sp in ("printer", "button", "access", "device", "schedules"):
                shot(page, f"{tag}-30-settings-{sp}")
        # guest page: enable, post a note as a stranger, approve it
        page.request.patch(args.base + "/api/settings", data={"guest": {"enabled": True, "mode": "approve"}})
        g = b.new_context(viewport=viewport).new_page()
        g.goto(args.base + "/note")
        g.fill("#text", "Hello from the hallway")
        g.click("#stickers button >> nth=0")
        shot(g, f"{tag}-40-guest")
        g.click("#go")
        expect(g.locator("#msg")).to_contain_text("approved")
        page.goto(args.base + "/settings/inbox")
        expect(page.locator("text=Hello from the hallway")).to_be_visible()
        shot(page, f"{tag}-41-inbox")
        page.click("button:has-text('Print it')")
        expect(page.locator("text=Nothing waiting.").first).to_be_visible()
        # Remote: add a sender, push a message through the mock inbox, see it in History › Remote
        page.goto(args.base + "/settings/email")
        page.click("text=Add a person")
        page.fill("#sn", "Sam")
        page.fill("input[aria-label='Address or ID']", "sam@example.com")
        page.click(".sheetf button:has-text('Save')")
        expect(page.locator("text=sam@example.com").first).to_be_visible()
        shot(page, f"{tag}-50-remote")
        page.request.post(args.base + "/api/dev/inbound", data={"channel": "email", "sender_id": "sam@example.com",
                          "sender_name": "Sam", "subject": "Dinner", "body": "Back at 7, put the oven on",
                          "external_id": f"smoke:{tag}"})
        page.goto(args.base + "/history")
        page.click(".chip:has-text('Remote')")
        expect(page.locator("a.hcard:has-text('From Sam: Dinner')").first).to_be_visible()
        page.locator("a.hcard").first.click()
        expect(page.locator(".sheetf .receipt img")).to_be_visible()
        page.wait_for_timeout(400)
        shot(page, f"{tag}-51-remote-history")
        page.keyboard.press("Escape")
        # Create › Draw: scribble with real pointer events
        page.goto(args.base + "/")
        page.click("button[role=tab]:has-text('Draw')")
        box = page.locator("canvas.draw").bounding_box()
        page.mouse.move(box["x"] + 40, box["y"] + 40)
        page.mouse.down()
        for i in range(12):
            page.mouse.move(box["x"] + 40 + i * 20, box["y"] + 40 + (i % 3) * 30, steps=3)
        page.mouse.up()
        expect(page.locator("button.btn-print")).to_be_enabled()
        page.wait_for_timeout(500)
        shot(page, f"{tag}-60-draw")
        # Create › Image: upload a photo; the 1-bit result shows on the paper
        page.click("button[role=tab]:has-text('Image')")
        page.set_input_files("#pic2", str(Path(__file__).with_name("sample.jpg")))
        expect(page.locator(".canvas .receipt img").first).to_be_visible(timeout=10000)
        page.wait_for_timeout(1200)
        shot(page, f"{tag}-61-image")
        # Templates: fill and print the Wi-Fi card
        page.click("button[role=tab]:has-text('Templates')")
        page.click(".tcard:has-text('Wi-Fi for guests')")
        page.fill("#f-ssid", "HomeWiFi")
        page.fill("#f-password", "correct-horse")
        page.wait_for_timeout(900)
        shot(page, f"{tag}-62-template")
        page.click(".sheetf button.btn-print")
        printed_toast()
        # List mode: add two items, see the preview, print; the list empties once printed
        page.goto(args.base + "/create/list")
        for item in ("Milk", "Bread"):
            page.fill("input[aria-label='New item']", item + " " + tag)
            page.keyboard.press("Enter")
            expect(page.locator(f"text={item} {tag}")).to_be_visible()
        expect(page.locator(".receipt.img img")).to_be_visible(timeout=10000)
        shot(page, f"{tag}-63-list")
        page.click("button:has-text('Print the list')")
        printed_toast()
        expect(page.locator(f"text=Milk {tag}")).to_have_count(0, timeout=10000)
        # quick action chip
        page.click(".chip:has-text('Fortune')")
        expect(page.locator(".toastf")).to_contain_text("fortune")
        extra = getattr(sys.modules[__name__], "EXTRA", None)
        if extra:
            extra(page, tag)
        b.close()


run({"width": 390, "height": 844}, "phone")
run({"width": 1200, "height": 800}, "desk")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("smoke OK ->", shots)
