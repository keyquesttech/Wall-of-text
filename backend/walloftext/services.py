"""Builds and wires every long-lived object. `WOT_HW=real|mock` picks hardware."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

from PIL import Image

from .auth.passwords import PasswordFile
from .auth.sessions import LoginLimiter, SessionStore
from .config import Settings
from .events import EventBus
from .hw.button import GestureDetector
from .hw.led import Led
from .hw.manager import Hardware, SwitchableLed
from .hw.led_controller import LedController
from .hw.system import MockSystemInfo, SystemInfo
from .net.nm import FakeNetworkManager, NmcliClient
from .net.wifi import WifiManager, WifiStatus
from .printer.drivers import EscposUsbPrinter, MockPrinter
from .queue.worker import PrintQueue
from .render.document import Renderer
from .render.fonts import FontRegistry
from .render.slips import connected_slip, setup_slip
from .store.db import Store
from .store.settings import AppSettings

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    store: Store
    passwords: PasswordFile
    sessions: SessionStore
    limiter: LoginLimiter
    events: EventBus
    nm: object
    wifi: WifiManager
    printer: object
    led: Led
    system: SystemInfo
    app_settings: AppSettings = None
    fonts: FontRegistry = None
    renderer: Renderer = None
    queue: PrintQueue = None
    button: object = None  # kept for older code; the live one is hw.button
    hw: Hardware = None
    loop: asyncio.AbstractEventLoop | None = None
    extras: dict = field(default_factory=dict)
    led_ctl: LedController = None

    # ----------------------------------------------------------- printing --
    def print_image(self, img: Image.Image, source: str, title: str, document: dict | None = None,
                    copies: int = 1, held_until: float | None = None, meta: dict | None = None) -> int:
        return self.queue.enqueue(img, source, title, document, copies, held_until, meta)

    def print_document(self, document: dict, source: str, title: str, copies: int = 1,
                       held_until: float | None = None, meta: dict | None = None) -> int:
        result = self.renderer.render(document)
        return self.print_image(result.image, source, title, document, copies, held_until, meta)

    async def print_setup_slip(self) -> None:
        if self.queue.status()["state"] not in ("ready", "printing"):
            log.info("printer not ready; setup slip skipped")
            return
        img = setup_slip(self.settings.fonts_dir, self.passwords.state.setup_wifi_password)
        self.print_image(img, "System", "Setup slip")

    async def print_connected_slip(self, ssid: str, ip: str | None) -> None:
        if self.queue.status()["state"] not in ("ready", "printing"):
            return
        img = connected_slip(self.settings.fonts_dir, ssid, ip)
        self.print_image(img, "System", "Connected")

    # ------------------------------------------------------------ button --
    def on_gesture(self, gesture: str) -> None:
        """May be called from the GPIO thread."""
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._handle_gesture(gesture)))

    async def _handle_gesture(self, gesture: str) -> None:
        from . import actions

        log.info("button: %s", gesture)
        self.events.publish("button", {"gesture": gesture})
        if gesture == "reset":
            await self.wifi.reset()
            self.led_ctl.update()
            return
        action = self.app_settings.get("button").get(gesture, "none")
        try:
            msg = await actions.run(self, action, source="Button")
        except Exception:
            log.exception("button action %s failed", action)
            msg = "That didn't work."
        self.events.publish("toast", {"message": f"Button: {msg}"})

    def on_reset_armed(self) -> None:
        self.led.set("triple_blink")

    # -------------------------------------------------------------- misc --
    def on_wifi_change(self, status: WifiStatus) -> None:
        self.events.publish("wifi", status.to_dict())

    def on_setup_wifi_password_change(self, psk: str) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.wifi.apply_ap_password(psk)))


def build(settings: Settings | None = None, nm=None) -> Services:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    passwords = PasswordFile(settings.password_file)
    sessions = SessionStore(store)
    events = EventBus()
    real = settings.hw == "real"

    if nm is None:
        nm = NmcliClient() if real else FakeNetworkManager()
        if not real and os.environ.get("WOT_MOCK_ONLINE"):
            nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
            nm.simulate_boot_autoconnect()
    printer = EscposUsbPrinter(settings.printer_device) if real else MockPrinter(settings.mock_printer_dir)
    system = SystemInfo() if real else MockSystemInfo()
    led = SwitchableLed()  # the real LED (if any) is plugged in by Hardware below

    wifi = WifiManager(nm=nm, settings=settings, ap_password=lambda: passwords.state.setup_wifi_password)
    app_settings = AppSettings(store)
    fonts = FontRegistry(settings.fonts_dir, settings.data_dir / "fonts")
    queue = PrintQueue(store, printer, events, app_settings.all)
    svc = Services(settings=settings, store=store, passwords=passwords, sessions=sessions,
                   limiter=LoginLimiter(), events=events, nm=nm, wifi=wifi, printer=printer,
                   led=led, system=system, app_settings=app_settings, fonts=fonts,
                   renderer=Renderer(fonts, app_settings.all), queue=queue)

    svc.led_ctl = LedController(led, app_settings.all)
    events.listeners.append(svc.led_ctl.on_event)
    app_settings.listeners.append(lambda merged: events.publish("settings", merged))
    detector = GestureDetector(svc.on_gesture, svc.on_reset_armed)
    # Button, panel light, fan and LED strips: built from Settings, rebuilt when they change
    svc.hw = Hardware(svc, real, detector)
    svc.hw.led = led
    svc.hw.apply(force=True)
    svc.button = svc.hw.button
    events.listeners.append(svc.hw.on_event)

    from .scheduler.engine import Scheduler
    from .sources.hub import Sources

    svc.extras["sources"] = Sources(svc)
    svc.extras["scheduler"] = Scheduler(svc)
    from .usb_backup import UsbBackup
    svc.extras["usb_backup"] = UsbBackup(svc)
    from .restarts import ScheduledRestart
    svc.extras["restart"] = ScheduledRestart(svc)
    from .remote.inbox import Inbox

    svc.extras["inbox"] = Inbox(svc)
    from .templates_lists import Lists, Templates

    svc.extras["templates"] = Templates(svc)
    svc.extras["lists"] = Lists(svc)
    from .remote.email_imap import EmailAdapter
    from .remote.manager import RemoteManager
    from .remote.mock import MockAdapter
    from .remote.pipeline import Pipeline
    from .remote.secrets import Secrets
    from .remote.telegram import TelegramAdapter

    secrets_store = Secrets(settings.data_dir / "secrets.json")
    svc.extras["secrets"] = secrets_store
    adapters = {"email": EmailAdapter(secrets_store), "telegram": TelegramAdapter(secrets_store, store)}
    if not real:
        adapters["mock"] = MockAdapter(settings.data_dir / "mock-inbox")
    pipeline = Pipeline(svc)
    svc.extras["remote"] = RemoteManager(svc, pipeline, adapters)
    queue.on_done.append(pipeline.on_job_done)
    passwords.on_gui_change.append(lambda: sessions.revoke_all())
    passwords.on_wifi_change.append(svc.on_setup_wifi_password_change)
    wifi.on_change.append(svc.on_wifi_change)
    wifi.on_setup.append(svc.print_setup_slip)
    wifi.on_online.append(svc.print_connected_slip)
    return svc
