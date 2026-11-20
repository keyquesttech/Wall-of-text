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
