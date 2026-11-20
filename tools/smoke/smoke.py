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
        shot(page, f"{tag}-01-create-empty")
        page.fill("#note", "Buy milk\nand call Grandma at six")
        page.wait_for_timeout(900)
        expect(page.locator(".paper img")).to_be_visible()
        shot(page, f"{tag}-02-create-typed")
        page.click("button.btn-print")
        expect(page.locator(".pm")).to_be_visible()
        page.wait_for_timeout(300)
        shot(page, f"{tag}-03-printing")
        expect(page.locator(".pm-text")).to_have_text("Printed", timeout=15000)
        page.wait_for_timeout(700)
        shot(page, f"{tag}-04-printed")
        page.click(".pm-actions .btn-green")
        page.click(".pill")
        expect(page.locator(".sheet")).to_be_visible()
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
        page.wait_for_timeout(500)
        page.locator("a.lrow").first.click()
        expect(page.locator(".sheet .paper img")).to_be_visible()
        page.wait_for_timeout(400)
        shot(page, f"{tag}-11-history-detail")
        page.keyboard.press("Escape")
        page.request.post(args.base + "/api/dev/net-state", data={"printer_offline": True})
        page.goto(args.base + "/")
        expect(page.locator(".banner")).to_contain_text("offline", timeout=8000)
        shot(page, f"{tag}-12-offline-banner")
        page.request.post(args.base + "/api/dev/net-state", data={"printer_offline": False})
        # Schedules: create from a starter, edit, preview
        page.goto(args.base + "/schedules")
        page.click("text=New schedule")
        page.click(".sheet >> text=Daily fortune")
        page.wait_for_url("**/schedules/*")
        expect(page.locator("#sname")).to_have_value("Daily fortune")
        page.click("text=Preview")
        expect(page.locator(".paper img")).to_be_visible(timeout=10000)
        page.wait_for_timeout(300)
        shot(page, f"{tag}-20-schedule-editor")
        page.click("button.btn-green:has-text('Save')")
        page.wait_for_url(args.base + "/schedules")
        page.wait_for_timeout(400)
        shot(page, f"{tag}-21-schedules")
        # every settings page renders without errors
        for sp in ["printer", "fonts", "button", "schedules", "history", "weather", "calendars", "tasks",
                   "remote", "access", "wifi", "device", "display"]:
            page.goto(args.base + "/settings/" + sp)
            expect(page.locator("h1")).not_to_have_text("Not found")
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
        page.goto(args.base + "/settings/access")
        expect(page.locator("text=Hello from the hallway")).to_be_visible()
        shot(page, f"{tag}-41-inbox")
        page.click("button:has-text('Print it')")
        expect(page.locator("text=Nothing waiting.").first).to_be_visible()
        # Remote: add a sender, push a message through the mock inbox, see it in History › Remote
        page.goto(args.base + "/settings/remote")
        page.click("text=Add a person")
        page.fill("#sn", "Sam")
        page.fill("input[aria-label='Address or ID']", "sam@example.com")
        page.click(".sheet button.btn-green:has-text('Save')")
        expect(page.locator("text=sam@example.com").first).to_be_visible()
        shot(page, f"{tag}-50-remote")
        page.request.post(args.base + "/api/dev/inbound", data={"channel": "email", "sender_id": "sam@example.com",
                          "sender_name": "Sam", "subject": "Dinner", "body": "Back at 7, put the oven on",
                          "external_id": f"smoke:{tag}"})
        page.goto(args.base + "/history")
        page.click(".chip:has-text('Remote')")
        expect(page.locator("text=From Sam: Dinner").first).to_be_visible()
        page.locator("a.lrow").first.click()
        expect(page.locator(".sheet .paper img")).to_be_visible()
        page.wait_for_timeout(400)
        shot(page, f"{tag}-51-remote-history")
        page.keyboard.press("Escape")
        # Create › Draw: scribble with real pointer events
        page.goto(args.base + "/")
        page.click(".chip[role=tab]:has-text('Draw')")
        box = page.locator("canvas.draw").bounding_box()
        page.mouse.move(box["x"] + 40, box["y"] + 40)
        page.mouse.down()
        for i in range(12):
            page.mouse.move(box["x"] + 40 + i * 20, box["y"] + 40 + (i % 3) * 30, steps=3)
        page.mouse.up()
        expect(page.locator(".paper img")).to_be_visible(timeout=8000)
        page.wait_for_timeout(500)
        shot(page, f"{tag}-60-draw")
        # Create › Image: upload a photo
        page.click(".chip[role=tab]:has-text('Image')")
        page.set_input_files("#pic2", str(Path(__file__).with_name("sample.jpg")))
        expect(page.locator(".paper img")).to_be_visible(timeout=10000)
        page.wait_for_timeout(1200)
        shot(page, f"{tag}-61-image")
        # Templates: fill and print the Wi-Fi card
        page.click(".chip[role=tab]:has-text('Templates')")
        page.click(".tcard:has-text('Wi-Fi for guests')")
        page.fill("#f-ssid", "HomeWiFi")
        page.fill("#f-password", "correct-horse")
        page.wait_for_timeout(900)
        shot(page, f"{tag}-62-template")
        page.click(".sheet button.btn-green:has-text('Print')")
        expect(page.locator(".pm-text")).to_have_text("Printed", timeout=15000)
        page.click(".pm-actions .btn-green")
        # List: add two items and print
        page.click(".chip[role=tab]:has-text('List')")
        for item in ("Milk", "Bread"):
            page.fill("input[aria-label='New item']", item + " " + tag)
            page.keyboard.press("Enter")
            expect(page.locator(f"text={item} {tag}")).to_be_visible()
        shot(page, f"{tag}-63-list")
        # quick action chip
        page.click(".chip:has-text('Fortune')")
        expect(page.locator(".toast")).to_contain_text("fortune")
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
