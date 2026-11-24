"""FastAPI application: middleware (captive portal, sign-in, cross-site checks)
and static serving. Routes live in `walloftext.api`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import access as access_api
from .api import actions as actions_api
from .api import backup as backup_api
from .api import auth as auth_api
from .api import dev as dev_api
from .api import device as device_api
from .api import fortunes as fortunes_api
from .api import google as google_api
from .api import printing as printing_api
from .api import remote as remote_api
from .api import schedules as schedules_api
from .api import settings as settings_api
from .api import templates as templates_api
from .api import wifi as wifi_api
from .auth.sessions import COOKIE_NAME
from .config import AP_ADDRESS, HOSTNAME, LOCAL_ADDRESS, Settings
from .net.captive import SETUP_URL, host_only, should_redirect
from .net.wifi import AP_MODES
from .services import Services, build

log = logging.getLogger(__name__)

# Paths anyone may load without signing in.
OPEN_PREFIXES = ("/ui/", "/fonts/", "/favicon", "/manifest", "/apple-touch-icon", "/icons/")
OPEN_PATHS = {"/signin", "/api/auth/login", "/api/auth/status", "/api/health", "/tokens.css",
              "/note", "/api/note", "/api/guest"}
AP_OPEN_PATHS = {"/setup", "/api/wifi/status", "/api/wifi/scan", "/api/wifi/connect"}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    svc = services or build(settings)
    s = svc.settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio

        svc.loop = asyncio.get_running_loop()
        svc.events.loop = svc.loop
        svc.queue.start()
        svc.led_ctl.update()
        svc.extras["scheduler"].start()
        svc.extras["remote"].reconcile()
        await svc.wifi.start()

        async def watch_password_file():
            # Edits to the file apply without a request arriving (e.g. re-key the AP).
            while True:
                await asyncio.sleep(5)
                try:
                    svc.passwords.refresh()
                    svc.sessions.purge_expired()
                except Exception:
                    log.exception("password file watch failed")

        watcher = asyncio.create_task(watch_password_file())
        from . import watchdog

        def healthy() -> bool:
            t = svc.queue._thread
            return t is not None and t.is_alive()

        dog = asyncio.create_task(watchdog.run(healthy))
        yield
        dog.cancel()
        watcher.cancel()
        await svc.wifi.stop()
        await svc.extras["scheduler"].stop()
        await svc.extras["remote"].stop()
        svc.queue.stop()
        if svc.button:
            svc.button.close()
        svc.led.close()

    app = FastAPI(title="Wall of Text", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs" if s.is_mock else None, redoc_url=None)
    app.state.svc = svc

    ip_cache: dict = {"at": -1e9, "ips": []}

    def own_hosts() -> set[str]:
        import time

        hosts = {LOCAL_ADDRESS, HOSTNAME, AP_ADDRESS, "localhost", "127.0.0.1"}
        now = time.monotonic()
        if now - ip_cache["at"] > 10:
            try:
                ip_cache["ips"] = list(svc.nm.all_ips())
            except Exception:
                ip_cache["ips"] = []
            ip_cache["at"] = now
        hosts.update(ip_cache["ips"])
        hosts.update(h.strip().lower() for h in s.extra_hosts if h.strip())
        if svc.wifi.status.ip:
            hosts.add(svc.wifi.status.ip)
        return hosts

    def signed_in(request: Request) -> bool:
        if svc.store.get("ask_for_password", "1") == "0":
            return True
        return svc.sessions.valid(request.cookies.get(COOKIE_NAME))

    @app.middleware("http")
    async def gatekeeper(request: Request, call_next):
        path = request.url.path
        host = host_only(request.headers.get("host"))
        ap_mode = svc.wifi.status.mode in AP_MODES
        hosts = own_hosts()

        # 1. Captive portal (AP modes only).
        if ap_mode and path != "/setup" and not path.startswith(("/ui/", "/fonts/", "/api/")) \
                and should_redirect(path, host, hosts):
            return RedirectResponse(SETUP_URL, status_code=302, headers={"Cache-Control": "no-store"})
        if ap_mode and path == "/":
            return RedirectResponse("/setup", status_code=302, headers={"Cache-Control": "no-store"})

        # 2. Password file changes apply at once.
        svc.passwords.refresh()

        # 3. Cross-site request rejection on mutating routes.
        if request.method in MUTATING:
            if host and host not in hosts:
                return JSONResponse({"error": "bad_host"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and host_only(origin.split("://", 1)[-1]) not in hosts:
                return JSONResponse({"error": "bad_origin"}, status_code=403)
            ctype = request.headers.get("content-type", "")
            has_body = request.headers.get("content-length", "0") not in ("", "0") or \
                "transfer-encoding" in request.headers
            if path.startswith("/api/") and has_body and \
                    not ctype.startswith(("application/json", "multipart/form-data")):
                return JSONResponse({"error": "json_required"}, status_code=415)

        # 4. Sign-in.
        request.state.signed_in = signed_in(request)
        is_open = path in OPEN_PATHS or path.startswith(OPEN_PREFIXES) or (ap_mode and path in AP_OPEN_PATHS)
        if s.is_mock and path.startswith("/api/dev/"):
            is_open = True
        if not is_open and not request.state.signed_in:
            if path.startswith("/api/"):
                return JSONResponse({"error": "sign_in_required"}, status_code=401)
            nxt = path if path.startswith("/") and not path.startswith("//") else "/"
            return RedirectResponse(f"/signin?next={nxt}", status_code=302)

        response: Response = await call_next(request)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Content-Security-Policy",
                     "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                     "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; "
                     "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    app.include_router(auth_api.router)
    app.include_router(wifi_api.router)
    app.include_router(device_api.router)
    app.include_router(printing_api.router)
    app.include_router(settings_api.router)
    app.include_router(actions_api.router)
    app.include_router(schedules_api.router)
    app.include_router(google_api.router)
    app.include_router(fortunes_api.router)
    app.include_router(access_api.router)
    app.include_router(backup_api.router)
    app.include_router(remote_api.router)
    app.include_router(templates_api.router)
    if s.is_mock:
        app.include_router(dev_api.router)

    # ------------------------------------------------------------ pages --
    ui = s.setup_ui_dir

    def page(name: str) -> FileResponse:
        return FileResponse(ui / name, headers={"Cache-Control": "no-store"})

    @app.get("/signin", include_in_schema=False)
    async def signin_page():
        return page("signin.html")

    @app.get("/note", include_in_schema=False)
    async def note_page():
        return page("note.html")

    @app.get("/setup", include_in_schema=False)
    async def setup_page(request: Request):
        if svc.wifi.status.mode not in AP_MODES and not request.state.signed_in:
            return RedirectResponse("/signin?next=/setup", status_code=302)
        return page("setup.html")

    tokens = s.setup_ui_dir.parent / "design-handoff" / "tokens.css"

    @app.get("/tokens.css", include_in_schema=False)
    async def tokens_css():
        if tokens.exists():
            return FileResponse(tokens, media_type="text/css")
        return Response("/* design-handoff/tokens.css not in this build */", media_type="text/css")

    if s.is_mock:
        @app.get("/dev", include_in_schema=False)
        async def dev_page():
            return page("dev.html")

    app.mount("/ui", StaticFiles(directory=ui), name="ui")
    if s.fonts_dir.exists():
        app.mount("/fonts", StaticFiles(directory=s.fonts_dir), name="fonts")

    frontend = s.frontend_dir
    if (frontend / "index.html").exists():
        if (frontend / "assets").exists():
            app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
        if (frontend / "icons").exists():
            app.mount("/icons", StaticFiles(directory=frontend / "icons"), name="icons")

        @app.get("/manifest.webmanifest", include_in_schema=False)
        async def manifest():
            return FileResponse(frontend / "manifest.webmanifest", media_type="application/manifest+json")

        @app.get("/apple-touch-icon.png", include_in_schema=False)
        async def touch_icon():
            return FileResponse(frontend / "icons" / "apple-touch-icon.png")

        @app.get("/settings-basic", include_in_schema=False)
        async def basic_settings():
            return page("home.html")

        # SPA: every other GET that isn't an API call gets index.html (client-side routing).
        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": "not_found"}, status_code=404)
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        # Phase 1 placeholder until the Preact app is built.
        @app.get("/", include_in_schema=False)
        async def home():
            return page("home.html")

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings()
    uvicorn.run(create_app(s), host="0.0.0.0", port=s.port, log_level="info",
                access_log=False)  # access logs off: never log /api/wifi/* bodies or tokens


if __name__ == "__main__":
    main()
