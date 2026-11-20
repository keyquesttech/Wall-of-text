#!/usr/bin/env python3
"""Tiny port-80 server for the captive-portal spike. Logs every request
(Host, path, User-Agent) and redirects connectivity probes to /setup.
Run by hotspot_test.sh; can also be run alone: sudo python3 captive_probe_server.py"""
import argparse
import datetime
import http.server

PAGE = b"""<!doctype html><meta name=viewport content="width=device-width"><title>Spike</title>
<body style="font:20px system-ui;padding:24px;background:#111;color:#eee"><h1>Spike captive page</h1>
<p>If you see this inside the Wi-Fi sign-in sheet, the captive portal works.</p>"""

ap = argparse.ArgumentParser()
ap.add_argument("--log", default="captive_requests.log")
ap.add_argument("--port", type=int, default=80)
args = ap.parse_args()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        with open(args.log, "a") as fh:
            fh.write(f"{datetime.datetime.now():%H:%M:%S} {self.client_address[0]} {host} {self.path} "
                     f"| {self.headers.get('User-Agent', '')}\n")
        if self.path == "/setup":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(PAGE)
            return
        self.send_response(302)
        self.send_header("Location", "http://10.42.0.1/setup")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("0.0.0.0", args.port), H).serve_forever()
