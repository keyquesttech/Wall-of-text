#!/usr/bin/env python3
"""Make a Google Tasks token on your PC, then upload it in Settings › Connections › Google Tasks.

Why on the PC: Google's device flow doesn't allow the Tasks scope, and the
normal installed-app flow needs a browser with a loopback redirect, which the
PC has (BUILD_PLAN 9.1).

One-time Google Cloud setup (free):
  1. https://console.cloud.google.com/ → create a project.
  2. APIs & Services → Library → enable "Google Tasks API".
  3. APIs & Services → OAuth consent screen → External → add yourself as a user.
     Then set Publishing status to **In production** (in "Testing", Google expires
     the token after 7 days). It stays "unverified"; that's fine for personal use.
  4. Credentials → Create credentials → OAuth client ID → Desktop app.
     Download the JSON (client_secret_….json).

Run (Windows PowerShell or any terminal, Python 3.9+, no extra packages):
    python tools/google_auth.py path\\to\\client_secret_XXXX.json
It opens your browser, you sign in and allow read-only Tasks access, and it
writes walloftext-google-token.json next to this script. Upload that file.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/tasks.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    cfg = json.loads(Path(sys.argv[1]).read_text())
    cfg = cfg.get("installed") or cfg.get("web") or cfg
    client_id, client_secret = cfg["client_id"], cfg["client_secret"]

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = "Done. You can close this tab and go back to the terminal." if "code" in q else "Something went wrong."
            self.wfile.write(f"<p style='font:20px sans-serif'>{msg}</p>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{srv.server_port}/"
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    print("Opening your browser to sign in to Google…\nIf it doesn't open, paste this link:\n" + url)
    webbrowser.open(url)
    t.join(timeout=300)
    srv.server_close()
    if result.get("state") != state or "code" not in result:
        sys.exit(f"Sign-in didn't finish: {result.get('error', 'no reply')}")
    data = urllib.parse.urlencode({
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier,
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data)) as r:
        tok = json.loads(r.read())
    if "refresh_token" not in tok:
        sys.exit("Google didn't return a refresh token. Remove the app's access at "
                 "https://myaccount.google.com/permissions and run this again.")
    out = Path(__file__).with_name("walloftext-google-token.json")
    out.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret,
                               "refresh_token": tok["refresh_token"], "scopes": [SCOPE]}, indent=1))
    print(f"Saved {out}\nUpload it in Wall Printer: Settings › Connections › Google Tasks.")


if __name__ == "__main__":
    main()
