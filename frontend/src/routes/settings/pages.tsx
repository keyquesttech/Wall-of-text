// Settings sub-pages; SETTINGS_PAGES at the end sets the groups and their order on Settings. DESIGN REVIEW: built from the shared
// components without the handoff's Settings mockups.
import type { FunctionComponent } from "preact";
import { signal } from "@preact/signals";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, get, send, upload, type FontInfo } from "../../lib/api";
import { inboxWaiting, printer, settings, wifi } from "../../lib/state";
import { IconBulb, IconCalendar, IconClock, IconCloud, IconDevice, IconEye, IconFont, IconHistory, IconLock, IconMail, IconPlus, IconPrinter, IconStar, IconTrash, IconFan, IconStrip, IconRoll, IconInbox, IconNote, IconButton, IconBackup, IconAlarm, IconBot, IconWifi } from "../../components/icons";
import { Banner, Chevron, Seg, Sheet, timeAgo, toast, Toggle, ToggleRow, Topbar } from "../../components/ui";
import { AccessPage, useBack, WifiPage } from "../Settings";
import { EmailPage, TelegramConnection, TelegramRemove } from "./remote";

export interface SettingsPage {
  id: string;
  title: string;
  group: string;
  Component: FunctionComponent;
  meta?: () => string;
  Icon?: (p: any) => any;
}

function useSettings(): [any, (patch: any) => Promise<void>] {
  const s = settings.value;
  const patch = async (p: any) => {
    settings.value = await api.patchSettings(p);
  };
  return [s, patch];
}

// ---------------------------------------------------------------- Printer --
function PrinterPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  const p = s.printer;
  return (
    <>
      <Topbar title="Printer" back={back} />
      <div class="glass card">
        <label class="field-label" for="dark" style="margin-top:0">Print darkness</label>
        <input id="dark" type="range" min={40} max={200} step={10} value={p.darkness}
          onChange={(e) => patch({ printer: { darkness: Number((e.target as HTMLInputElement).value) } })} />
        <div class="row dim tiny" style="justify-content:space-between"><span>Lighter, fewer jams</span><span>Darker</span></div>
        <label class="field-label">Speed</label>
        <Seg label="Speed" value={p.speed} onChange={(v) => patch({ printer: { speed: v } })}
          options={[{ value: "slow", label: "Careful" }, { value: "normal", label: "Normal" }, { value: "fast", label: "Fast" }]} />
        <label class="field-label">Extra paper at the end</label>
        <Seg label="Extra feed" value={String(p.extra_feed)} onChange={(v) => patch({ printer: { extra_feed: Number(v) } })}
          options={["0", "1", "2", "4"].map((v) => ({ value: v, label: v === "0" ? "None" : v === "1" ? "1 line" : `${v} lines` }))} />
      </div>
      <div class="glass grp" style="margin-top:12px">
        <ToggleRow label="Paper saver" sub="Tighter spacing and no blank space at the end." checked={p.paper_saver}
          onChange={(v) => patch({ printer: { paper_saver: v } })} />
        <ToggleRow label="Rotate prints 180°" sub="Turns every slip round so it reads the right way up as it hangs from the printer." checked={p.rotate_180 ?? true}
          onChange={(v) => patch({ printer: { rotate_180: v } })} />
      </div>
      <div class="glass grp" style="margin-top:12px">
        <button class="lrow" onClick={() => api.testPage().then(() => toast("Printing a test page"))}>Print a test page</button>
      </div>
      <p class="dim tiny" style="margin:8px 6px">The test page shows the darkness and speed, a ruler and grey tones.</p>
    </>
  );
}

// ------------------------------------------------------------- Paper roll --
function PaperPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  const p = s.printer;
  return (
    <>
      <Topbar title="Paper roll" back={back} />
      <div class="glass grp">
        <div class="lrow kv-row"><span class="grow">Left on the roll</span>
          <span class="meta">About {printer.value?.paper_percent ?? 100}%{printer.value?.paper_left_m != null ? ` · ${printer.value.paper_left_m} m` : ""}</span></div>
        <div class="lrow">
          <div class="grow"><div class="title">Roll length</div><div class="sub" style="white-space:normal">Printed on the roll's box, often 10, 15 or 30 m.</div></div>
          <input type="number" class="input" style="width:96px" min={1} max={100} step={0.5} value={p.roll_length_m ?? 10} aria-label="Roll length in metres"
            onChange={(e) => { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= 100) patch({ printer: { roll_length_m: v } }).then(() => api.queue().then((q) => (printer.value = q.printer))); }} />
          <span class="dim">m</span>
        </div>
        <button class="lrow" onClick={() => api.newRoll().then((x) => { printer.value = x; toast("Paper counter reset"); })}>I loaded a new roll</button>
      </div>
      <p class="dim tiny" style="margin:8px 6px">The printer can't measure the roll, so this is an estimate from how much has been printed, the roll length and the calibration below.</p>
      <Calibration mmPerRow={p.mm_per_row ?? 0.125} />
    </>
  );
}

/** Paper length calibration: print two lines 800 dot rows apart, measure them, enter the gap. */
function Calibration(props: { mmPerRow: number }) {
  const [, patch] = useSettings();
  const [mm, setMm] = useState("");
  const [busy, setBusy] = useState(false);
  const nominal = Math.abs(props.mmPerRow - 0.125) < 1e-6;
  const save = async (measured: number | null) => {
    setBusy(true);
    try {
      const r = await send<any>("POST", "/api/printer/calibration", { measured_mm: measured });
      printer.value = { ...printer.value!, paper_percent: r.paper_percent, paper_left_m: r.paper_left_m };
      await patch({});
      setMm("");
      toast(measured ? "Calibrated" : "Back to the standard length");
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  const v = Number(mm.replace(",", "."));
  return (
    <>
      <h2 class="section">Calibrate length</h2>
      <div class="glass card stack">
        <p style="margin:0" class="small">Makes the paper estimate match your printer. It only changes the estimate, never what prints.</p>
        <ol class="small steps">
          <li>Print the calibration slip. It has two lines that should be 100 mm apart.</li>
          <li>Measure from the top edge of the top line to the top edge of the bottom line.</li>
          <li>Enter what you measured.</li>
        </ol>
        <button class="btn block" disabled={busy} onClick={() => send("POST", "/api/printer/calibration-print").then(() => toast("Printing the calibration slip"))}>Print calibration slip</button>
        <div class="row">
          <label class="sr-only" for="calmm">Measured gap in millimetres</label>
          <input id="calmm" class="input grow" inputMode="decimal" placeholder="Measured gap, e.g. 101.5" value={mm} onInput={(e) => setMm((e.target as HTMLInputElement).value)} />
          <span class="dim">mm</span>
        </div>
        <button class="btn-green block" disabled={busy || !(v >= 60 && v <= 140)} onClick={() => save(v)}>Save calibration</button>
        <p class="cap" style="margin:0">{nominal ? "Using the standard 8 dot rows per mm." : `Calibrated: 100 mm on the slip measured ${(props.mmPerRow * 800).toFixed(1)} mm.`}
          {!nominal && <> <button class="linkbtn" onClick={() => save(null)}>Reset</button></>}</p>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ Fonts --
function FontsPage() {
  const back = useBack();
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [s, patch] = useSettings();
  const file = useRef<HTMLInputElement>(null);
  const load = () => api.fonts().then(setFonts);
  useEffect(() => { load(); }, []);
  const onFile = async () => {
    const f = file.current?.files?.[0];
    if (!f) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("name", f.name.replace(/\.(ttf|otf)$/i, ""));
    try {
      const r = await upload<FontInfo>("/api/fonts", fd);
      toast(r.min_readable ? `Added. Readable from size ${r.min_readable}.` : "Added.");
      load();
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); if (file.current) file.current.value = ""; }
  };
  return (
    <>
      <Topbar title="Fonts" back={back} />
      <div class="glass grp">
        {fonts.map((f) => (
          <div class="lrow">
            <div class="grow">
              <div class="title">{f.name}</div>
              <div class="sub">{f.builtin ? "Built in" : "Uploaded"}{f.min_readable ? ` · readable from ${f.min_readable}` : ""}{s?.printer.default_font === f.id ? " · default" : ""}</div>
            </div>
            {s?.printer.default_font !== f.id && <button class="btn small" onClick={() => patch({ printer: { default_font: f.id } })}>Make default</button>}
            {!f.builtin && <button class="icon-btn" aria-label={`Remove ${f.name}`} onClick={() => send("DELETE", `/api/fonts/${f.id}`).then(load)}><IconTrash /></button>}
          </div>
        ))}
      </div>
      <input ref={file} type="file" accept=".ttf,.otf,font/ttf,font/otf" class="sr-only" id="fontfile" onChange={onFile} />
      <label for="fontfile" class="btn block" style="margin-top:14px" aria-disabled={busy}><IconPlus width={18} />{busy ? "Uploading…" : "Upload a font (.ttf or .otf)"}</label>
      <p class="dim tiny" style="margin:8px 6px">Thin fonts can vanish on thermal paper. After upload you'll see the smallest size that stays readable.</p>
      <label class="field-label">Default size</label>
      <Seg label="Default size" value={s?.printer.default_size ?? "M"} onChange={(v) => patch({ printer: { default_size: v } })}
        options={["S", "M", "L", "XL"].map((v) => ({ value: v, label: v }))} />
    </>
  );
}

// ------------------------------------------------------------ Button & LED --
// ---------------------------------------------------------------- Hardware --
// GPIO numbers are BCM ("GPIO17"); the header pin is shown next to each so it's easy to wire.
const HEADER: Record<number, number> = { 2: 3, 3: 5, 4: 7, 17: 11, 27: 13, 22: 15, 10: 19, 9: 21, 11: 23, 5: 29, 6: 31, 13: 33, 19: 35, 26: 37,
  14: 8, 15: 10, 18: 12, 23: 16, 24: 18, 25: 22, 8: 24, 7: 26, 12: 32, 16: 36, 20: 38, 21: 40 };
const RESERVED_PINS: Record<number, string> = { 2: "I2C", 3: "I2C", 14: "serial", 15: "serial" };
const pinLabel = (g: number) => `GPIO${g} · pin ${HEADER[g] ?? "?"}`;

interface HwStatus {
  real: boolean; spi: string[]; temperature_c: number | null; problems: Record<string, string>;
  button: { on: boolean; error?: string }; led: { on: boolean; error?: string };
  fan: { on: boolean; error?: string; speed?: number; temperature_c?: number | null; testing?: boolean };
  neopixel: { on: boolean; error?: string; strip_errors: Record<string, string>; live: { event: string; progress: number; frames: string[][] } | null };
}
/** Hardware status, polled while the page is open (fast while something animates). */
function useHw(fast = false): [HwStatus | null, () => void] {
  const [hw, setHw] = useState<HwStatus | null>(null);
  const load = () => { get<HwStatus>("/api/hw").then(setHw).catch(() => {}); };
  useEffect(() => { load(); const t = setInterval(load, fast ? 250 : 3000); return () => clearInterval(t); }, [fast]);
  return [hw, load];
}

/** GPIO picker: marks pins another device uses and the ones kept for I2C and the serial console. */
function PinSelect(props: { id: string; value: number; onChange: (v: number) => void; used: Record<number, string>; label: string; pins?: number[] }) {
  const pins = props.pins ?? Array.from({ length: 26 }, (_, i) => i + 2);
  return (
    <select id={props.id} class="input" style="flex:1;min-width:0;max-width:240px;margin-left:auto" aria-label={props.label} value={String(props.value)}
      onChange={(e) => props.onChange(Number((e.target as HTMLSelectElement).value))}>
      {pins.map((g) => {
        const note = g !== props.value && props.used[g] ? ` (${props.used[g]})` : RESERVED_PINS[g] ? ` (${RESERVED_PINS[g]})` : "";
        return <option value={String(g)}>{pinLabel(g)}{note}</option>;
      })}
    </select>
  );
}

/** Which device holds each pin, from the settings (mirrors backend hw/pins.py claims). */
function usedPins(s: any, except: string): Record<number, string> {
  const u: Record<number, string> = {};
  if (except !== "button" && s.button?.enabled !== false) u[s.button?.pin ?? 17] = "button";
  if (except !== "led" && s.led?.enabled !== false) u[s.led?.pin ?? 18] = "light";
  if (except !== "fan" && s.fan?.enabled) u[s.fan.pin] = "fan";
  if (except !== "neopixel" && s.neopixel?.enabled) {
    for (const st of s.neopixel.strips ?? []) for (const p of (st.pin === 20 ? [16, 19, 20, 21] : [9, 10, 11])) u[p] = "LED strip";
  }
  return u;
}

function HwError(props: { msg?: string | null }) {
  return props.msg ? <Banner>{props.msg}</Banner> : null;
}

function ButtonPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [actions, setActions] = useState<{ id: string; label: string }[]>([]);
  useEffect(() => { get<{ id: string; label: string }[]>("/api/actions").then(setActions); }, []);
  const [hw] = useHw();
  if (!s) return null;
  const on = s.button.enabled !== false;
  return (
    <>
      <Topbar title="Button" back={back} />
      <HwError msg={hw?.button.error} />
      <div class="glass grp">
        <ToggleRow label="Use the button" sub="Switch off if no button is wired, or to stop presses doing anything." checked={on}
          onChange={(v) => patch({ button: { enabled: v } })} />
        {on && (
          <div class="lrow"><label for="bpin" style="flex:none">Connected to</label>
            <PinSelect id="bpin" label="Button GPIO pin" value={s.button.pin ?? 17} used={usedPins(s, "button")} onChange={(v) => patch({ button: { pin: v } })} />
          </div>
        )}
      </div>
      {on && (
        <>
          <p class="dim tiny" style="margin:8px 6px">Wire the button between that pin and a ground pin (GND). No resistor needed: the Pi's own pull-up is used.</p>
          <h2 class="section">What a press does</h2>
          <div class="glass grp">
            {(["single", "double", "long"] as const).map((g) => (
              <div class="lrow">
                <span style="flex:none">{g === "single" ? "Press" : g === "double" ? "Double press" : "Long press"}</span>
                <select class="input" style="flex:1;min-width:0;max-width:260px;margin-left:auto;text-overflow:ellipsis" aria-label={`${g} press action`} value={s.button[g]}
                  onChange={(e) => patch({ button: { [g]: (e.target as HTMLSelectElement).value } })}>
                  {actions.map((a) => <option value={a.id}>{a.label}</option>)}
                </select>
              </div>
            ))}
            <div class="lrow"><span class="grow">Hold for 30 seconds</span><span class="meta">Reset Wi-Fi (fixed)</span></div>
          </div>
          <p class="dim tiny" style="margin:8px 6px">Holding the button for 30 seconds always starts Wi-Fi setup again: the light blinks three times, then let go.</p>
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------ Panel light --
function LightPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [hw] = useHw();
  if (!s) return null;
  const led = s.led;
  const on = led.enabled !== false;
  const events: [string, string][] = [["idle", "Idle"], ["printing", "Printing"], ["message_waiting", "New message waiting"], ["paper_out", "Paper out"], ["error", "Error"]];
  return (
    <>
      <Topbar title="Panel light" back={back} />
      <HwError msg={hw?.led.error} />
      <div class="glass grp">
        <ToggleRow label="Use the panel light" sub="A single LED that shows what the printer is doing." checked={on}
          onChange={(v) => patch({ led: { enabled: v } })} />
        {on && (
          <div class="lrow"><label for="lpin" style="flex:none">Connected to</label>
            <PinSelect id="lpin" label="Light GPIO pin" value={led.pin ?? 18} used={usedPins(s, "led")} onChange={(v) => patch({ led: { pin: v } })} />
          </div>
        )}
      </div>
      {on && (
        <>
          <p class="dim tiny" style="margin:8px 6px">Wire the LED's long leg to that pin through a resistor (about 330 Ω), and its short leg to GND.</p>
          <h2 class="section">Look</h2>
          <div class="glass card">
            <label class="field-label" for="bright" style="margin-top:0">Brightness</label>
            <input id="bright" type="range" min={0} max={100} step={5} value={led.brightness}
              onChange={(e) => patch({ led: { brightness: Number((e.target as HTMLInputElement).value) } })} />
          </div>
          <h2 class="section">What it shows</h2>
          <div class="glass grp">
            {events.map(([k, label]) => (
              <div class="lrow">
                <span class="grow">{label}</span>
                <select class="input" style="width:auto" aria-label={`Light when ${label}`} value={led.patterns[k]}
                  onChange={(e) => patch({ led: { patterns: { [k]: (e.target as HTMLSelectElement).value } } })}>
                  <option value="off">Off</option><option value="solid">Solid</option><option value="slow_pulse">Slow pulse</option><option value="blink">Blink</option>
                </select>
              </div>
            ))}
          </div>
          <p class="dim tiny" style="margin:8px 6px">In Wi-Fi setup mode the light always pulses slowly.</p>
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------- Fan --
function FanPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [hw, reload] = useHw();
  if (!s) return null;
  const f = s.fan;
  const num = (k: string, min: number, max: number) => (e: Event) => {
    const v = Number((e.target as HTMLInputElement).value);
    if (v >= min && v <= max) patch({ fan: { [k]: v } });
  };
  return (
    <>
      <Topbar title="Fan" back={back} />
      <HwError msg={hw?.fan.error} />
      <div class="glass grp">
        <ToggleRow label="Use an extra fan" sub="A fan on a GPIO pin, through a transistor or MOSFET (or a 4-pin PWM fan's control wire)." checked={!!f.enabled}
          onChange={(v) => patch({ fan: { enabled: v } })} />
        {f.enabled && (
          <div class="lrow"><label for="fpin" style="flex:none">Connected to</label>
            <PinSelect id="fpin" label="Fan GPIO pin" value={f.pin} used={usedPins(s, "fan")} onChange={(v) => patch({ fan: { pin: v } })} />
          </div>
        )}
      </div>
      {f.enabled && (
        <>
          {hw?.fan.on && (
            <div class="glass card row" style="gap:16px">
              <span class="ico g"><IconFan class="i" /></span>
              <div class="grow">
                <div class="h3 num">{hw.fan.speed ?? 0}%{hw.fan.testing ? " · test" : ""}</div>
                <div class="cap">Pi at {hw.fan.temperature_c != null ? `${hw.fan.temperature_c.toFixed(1)} °C` : "—"}</div>
              </div>
              <button class="btn small" onClick={() => send("POST", "/api/hw/fan/test").then(() => { toast("Full speed for 5 seconds"); reload(); }).catch((e) => toast(e.message))}>Test</button>
            </div>
          )}
          <h2 class="section">How it runs</h2>
          <div class="glass card stack">
            <Seg label="Fan mode" value={f.mode} onChange={(v) => patch({ fan: { mode: v } })}
              options={[{ value: "temperature", label: "By temperature" }, { value: "always", label: "Always on" }]} />
            <p class="cap" style="margin:0">{f.mode === "always" ? `Runs at ${f.max_speed}% all the time.`
              : `Off below ${f.start_temp} °C. Starts at ${f.min_speed}% at ${f.start_temp} °C and speeds up to ${f.max_speed}% at ${f.full_temp} °C. Stops again below ${f.start_temp - 3} °C.`}</p>
          </div>
          <div class="glass grp" style="margin-top:12px">
            {f.mode === "temperature" && (
              <>
                <div class="lrow"><label for="fst" class="grow">Starts at</label>
                  <input id="fst" type="number" class="input" style="width:90px" min={30} max={80} value={f.start_temp} onChange={num("start_temp", 30, 80)} /><span class="dim">°C</span></div>
                <div class="lrow"><label for="fft" class="grow">Full speed at</label>
                  <input id="fft" type="number" class="input" style="width:90px" min={f.start_temp + 1} max={85} value={f.full_temp} onChange={num("full_temp", f.start_temp + 1, 85)} /><span class="dim">°C</span></div>
              </>
            )}
            <div class="lrow col">
              <label for="fmin" class="row" style="justify-content:space-between"><span>Minimum speed</span><span class="num">{f.min_speed}%</span></label>
              <input id="fmin" type="range" min={0} max={100} step={5} value={f.min_speed} onChange={num("min_speed", 0, Math.min(100, f.max_speed))} />
              <span class="cap">The slowest it reliably spins. A stopped fan gets a short full-power kick first.</span>
            </div>
            <div class="lrow col">
              <label for="fmax" class="row" style="justify-content:space-between"><span>Maximum speed</span><span class="num">{f.max_speed}%</span></label>
              <input id="fmax" type="range" min={10} max={100} step={5} value={f.max_speed} onChange={num("max_speed", Math.max(10, f.min_speed), 100)} />
            </div>
          </div>
          <h2 class="section">Wiring details</h2>
          <div class="glass grp">
            <div class="lrow"><label for="ffreq" class="grow">PWM frequency</label>
              <select id="ffreq" class="input" style="width:auto" value={String(f.frequency)} onChange={(e) => patch({ fan: { frequency: Number((e.target as HTMLSelectElement).value) } })}>
                {[100, 500, 1000, 5000, 10000].map((v) => <option value={String(v)}>{v >= 1000 ? `${v / 1000} kHz` : `${v} Hz`}</option>)}
              </select></div>
            <ToggleRow label="Inverted output" sub="For drivers where low means on (some PNP or P-channel boards)." checked={!!f.invert}
              onChange={(v) => patch({ fan: { invert: v } })} />
          </div>
          <p class="dim tiny" style="margin:8px 6px">Never connect a fan straight to a GPIO pin: drive it through a transistor or MOSFET with a flyback diode. If it whines, try a higher frequency; if it won't start slowly, raise the minimum speed.</p>
        </>
      )}
    </>
  );
}

// -------------------------------------------------------------- LED strip --
const EFFECTS: [string, string][] = [["off", "Off"], ["solid", "Solid"], ["breathe", "Breathe"], ["blink", "Blink"], ["chase", "Chase"],
  ["wipe", "Colour wipe"], ["rainbow", "Rainbow"], ["sparkle", "Sparkle"], ["progress", "Print progress"]];
const STRIP_EVENTS: [string, string][] = [["idle", "Idle"], ["printing", "Printing"], ["message_waiting", "Message waiting"],
  ["paper_out", "Paper out"], ["error", "Printer error / offline"], ["setup", "Wi-Fi setup"]];
const EFFECT_COLOURS: Record<string, number> = { off: 0, solid: 1, breathe: 1, blink: 2, chase: 3, wipe: 3, rainbow: 0, sparkle: 3, progress: 2 };
const COLOUR_HINT: Record<string, string[]> = { blink: ["On", "Off"], progress: ["Done", "To go"], sparkle: ["Sparkle", "Base", "Sparkle 2"] };

function StripPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const n = s?.neopixel;
  const [hw, reload] = useHw(!!n?.enabled);
  if (!s) return null;
  const strips: any[] = n.strips ?? [];
  const setStrips = (xs: any[]) => patch({ neopixel: { strips: xs } });
  const setEvent = (ev: string, p: any) => patch({ neopixel: { events: { [ev]: { ...n.events[ev], ...p } } } });
  const live = hw?.neopixel.live;
  const noSpi = hw?.real && n.enabled && !hw.spi.length;
  return (
    <>
      <Topbar title="LED strip" back={back} />
      <HwError msg={hw?.neopixel.error} />
      {noSpi && <Banner>SPI is switched off on the Pi. On the Pi, run <span class="mono">sudo bash deploy/enable_spi.sh</span> (add <span class="mono">--two</span> for a second strip), then restart it.</Banner>}
      <div class="glass grp">
        <ToggleRow label="Use WS2812 LED strips" sub="NeoPixel-style strips that show what the printer is doing." checked={!!n.enabled}
          onChange={(v) => patch({ neopixel: { enabled: v } })} />
      </div>
      {n.enabled && (
        <>
          {live && (
            <div class="glass card" aria-label="What the strips show now">
              <div class="row" style="justify-content:space-between"><span class="lbl">Live</span><span class="cap">{STRIP_EVENTS.find(([k]) => k === live.event)?.[1]}</span></div>
              {live.frames.map((fr) => (
                <div class="ledrow" aria-hidden="true">{fr.map((c) => <i style={{ background: c, boxShadow: c !== "#000000" ? `0 0 6px ${c}` : "none" }} />)}</div>
              ))}
            </div>
          )}
          <h2 class="section">Strips</h2>
          {strips.map((st, i) => (
            <>
              <HwError msg={hw?.neopixel.strip_errors[`strip${i}`] ?? hw?.problems[`strip${i}`]} />
              <div class="glass grp">
                <div class="lrow"><span class="grow h3" style="font-size:16px">Strip {i + 1}</span>
                  {strips.length > 1 && <button class="ib" aria-label={`Remove strip ${i + 1}`} onClick={() => setStrips(strips.filter((_, k) => k !== i))}><IconTrash class="i" /></button>}</div>
                <div class="lrow"><label for={`sp${i}`} style="flex:none">Data pin</label>
                  <PinSelect id={`sp${i}`} label={`Strip ${i + 1} data pin`} value={st.pin} pins={[10, 20]} used={{}} onChange={(v) => setStrips(strips.map((x, k) => (k === i ? { ...x, pin: v } : x)))} /></div>
                <div class="lrow"><label for={`sc${i}`} class="grow">Number of LEDs</label>
                  <input id={`sc${i}`} type="number" class="input" style="width:96px" min={1} max={450} value={st.count}
                    onChange={(e) => { const v = Number((e.target as HTMLInputElement).value); if (v >= 1 && v <= 450) setStrips(strips.map((x, k) => (k === i ? { ...x, count: v } : x))); }} /></div>
                <ToggleRow label="Reverse direction" sub="If effects run the wrong way along the strip." checked={!!st.reverse}
                  onChange={(v) => setStrips(strips.map((x, k) => (k === i ? { ...x, reverse: v } : x)))} />
              </div>
            </>
          ))}
          {strips.length < 2 && <button class="add-row" onClick={() => setStrips([...strips, { pin: strips[0]?.pin === 10 ? 20 : 10, count: 30, reverse: false }])}><IconPlus class="i" width={18} />Add a second strip</button>}
          <p class="dim tiny" style="margin:8px 6px">Up to 450 LEDs per strip. Strip 1 uses GPIO10 (header pin 19), strip 2 GPIO20 (pin 38). Power long strips from their own 5 V supply, join its ground to the Pi's, and add a level shifter if the first LED flickers.</p>

          <h2 class="section">Look</h2>
          <div class="glass grp">
            <div class="lrow col">
              <label for="nbr" class="row" style="justify-content:space-between"><span>Brightness</span><span class="num">{n.brightness}%</span></label>
              <input id="nbr" type="range" min={1} max={100} step={1} value={n.brightness} onChange={(e) => patch({ neopixel: { brightness: Number((e.target as HTMLInputElement).value) } })} />
            </div>
            <div class="lrow col">
              <label for="nqb" class="row" style="justify-content:space-between"><span>During quiet hours</span><span class="num">{n.quiet_brightness ? `${n.quiet_brightness}% of that` : "Off"}</span></label>
              <input id="nqb" type="range" min={0} max={100} step={5} value={n.quiet_brightness} onChange={(e) => patch({ neopixel: { quiet_brightness: Number((e.target as HTMLInputElement).value) } })} />
            </div>
            <div class="lrow col">
              <label for="nsp" class="row" style="justify-content:space-between"><span>Effect speed</span><span class="num">{n.speed}</span></label>
              <input id="nsp" type="range" min={1} max={100} step={1} value={n.speed} onChange={(e) => patch({ neopixel: { speed: Number((e.target as HTMLInputElement).value) } })} />
            </div>
            <div class="lrow"><label for="nord" class="grow">Colour order</label>
              <select id="nord" class="input" style="width:auto" value={n.order} onChange={(e) => patch({ neopixel: { order: (e.target as HTMLSelectElement).value } })}>
                {["GRB", "RGB", "BRG", "RBG", "GBR", "BGR"].map((o) => <option value={o}>{o}{o === "GRB" ? " (most strips)" : ""}</option>)}
              </select></div>
          </div>

          <h2 class="section">What it shows</h2>
          {STRIP_EVENTS.map(([ev, label]) => {
            const e = n.events[ev] ?? { effect: "off", colors: [] };
            const k = EFFECT_COLOURS[e.effect] ?? 1;
            const cols: string[] = [...(e.colors ?? [])];
            while (cols.length < k) cols.push(["#39ff88", "#000000", "#ff2e9a"][cols.length] ?? "#ffffff");
            return (
              <div class="glass grp">
                <div class="lrow"><span class="grow" style="font-weight:600">{label}</span>
                  <button class="btn small" onClick={() => send("POST", "/api/hw/neopixel/try", { event: ev }).then(() => { toast(`Showing “${label}” for 6 seconds`); reload(); }).catch((x) => toast(x.message))}>Try</button></div>
                <div class="lrow">
                  <label for={`ef-${ev}`} style="flex:none">Effect</label>
                  <select id={`ef-${ev}`} class="input" style="flex:1;min-width:0;max-width:220px;margin-left:auto" value={e.effect} onChange={(x) => setEvent(ev, { effect: (x.target as HTMLSelectElement).value, colors: cols })}>
                    {EFFECTS.map(([v, l]) => <option value={v}>{l}</option>)}
                  </select>
                </div>
                {k > 0 && (
                  <div class="lrow" style="gap:14px;flex-wrap:wrap">
                    <span style="flex:none">Colours</span>
                    {cols.slice(0, k).map((c, i) => (
                      <label class="swatch">
                        <input type="color" value={c} aria-label={`${label}: ${COLOUR_HINT[e.effect]?.[i] ?? `colour ${i + 1}`}`}
                          onChange={(x) => { const next = cols.slice(0, k); next[i] = (x.target as HTMLInputElement).value; setEvent(ev, { colors: next }); }} />
                        <span class="cap">{COLOUR_HINT[e.effect]?.[i] ?? (k > 1 ? `${i + 1}` : "")}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <p class="dim tiny" style="margin:8px 6px">Print progress fills the strip as a print comes out. Wi-Fi setup takes over whenever the printer is in setup mode.</p>
        </>
      )}
    </>
  );
}

// --------------------------------------------------------- Schedules prefs --
function SchedulePrefs() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  const sc = s.schedules;
  const q = sc.quiet_hours;
  return (
    <>
      <Topbar title="Schedules" back={back} />
      <h2 class="section">If the printer was off</h2>
      <div class="glass grp">
        {[["late_60", "Print late, up to an hour", "After an hour it's skipped and shows as Missed in History."],
          ["skip", "Skip it", "Missed prints never come out late."],
          ["always", "Always print when back", "Even if it's hours late."],
          ["notice", "Skip them and print a note", "When the printer is back, one short slip says how many prints were missed."]].map(([v, l, sub]) => (
          <button class="lrow" aria-pressed={sc.missed_policy === v} onClick={() => patch({ schedules: { missed_policy: v } })}>
            <div class="grow"><div class="title">{l}</div><div class="sub" style="white-space:normal">{sub}</div></div>
            {sc.missed_policy === v && <span aria-hidden="true">✓</span>}
          </button>
        ))}
      </div>
      <h2 class="section">Quiet hours</h2>
      <div class="glass grp">
        <ToggleRow label="Quiet hours" sub="Scheduled, guest and remote prints wait until they end. Your own prints always go." checked={q.enabled}
          onChange={(v) => patch({ schedules: { quiet_hours: { enabled: v } } })} />
        {q.enabled && (
          <div class="lrow">
            <span class="grow">From</span>
            <input type="time" class="input" style="width:130px" value={q.start} aria-label="Quiet from" onChange={(e) => patch({ schedules: { quiet_hours: { start: (e.target as HTMLInputElement).value } } })} />
            <span>to</span>
            <input type="time" class="input" style="width:130px" value={q.end} aria-label="Quiet until" onChange={(e) => patch({ schedules: { quiet_hours: { end: (e.target as HTMLInputElement).value } } })} />
          </div>
        )}
      </div>
      <h2 class="section">Limits</h2>
      <div class="glass grp">
        <div class="lrow">
          <div class="grow"><div class="title">Daily limit</div><div class="sub" style="white-space:normal">Most scheduled, guest and remote prints per day. 0 = no limit.</div></div>
          <input type="number" min={0} max={500} class="input" style="width:90px" value={sc.daily_limit} aria-label="Daily limit"
            onChange={(e) => patch({ schedules: { daily_limit: Number((e.target as HTMLInputElement).value) } })} />
        </div>
        <ToggleRow label="Holiday mode" sub="Pause every schedule." checked={sc.holiday_mode} onChange={(v) => patch({ schedules: { holiday_mode: v } })} />
      </div>
      <h2 class="section">Clock</h2>
      <div class="glass grp">
        <a class="lrow" href="/settings/time"><span class="grow">Date, time and time zone</span><span class="v">{sc.timezone}</span><Chevron /></a>
      </div>
    </>
  );
}

function HistoryPrefs() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  return (
    <>
      <Topbar title="History" back={back} />
      <div class="glass grp">
        <div class="lrow"><span class="grow">Keep up to</span>
          <select class="input" style="width:auto" value={s.history.max_items} aria-label="Items kept" onChange={(e) => patch({ history: { max_items: Number((e.target as HTMLSelectElement).value) } })}>
            {[50, 100, 200, 500, 1000, 2000, 0].map((n) => <option value={n}>{n ? `${n} prints` : "No limit"}</option>)}
          </select>
        </div>
        <div class="lrow"><span class="grow">For at most</span>
          <select class="input" style="width:auto" value={s.history.max_days} aria-label="Days kept" onChange={(e) => patch({ history: { max_days: Number((e.target as HTMLSelectElement).value) } })}>
            {[1, 3, 7, 14, 30, 90, 180, 365, 0].map((n) => <option value={n}>{n === 0 ? "Forever" : n === 1 ? "1 day" : n === 365 ? "1 year" : `${n} days`}</option>)}
          </select>
        </div>
      </div>
      <p class="dim tiny" style="margin:8px 6px">Whichever comes first. Each print keeps a small picture of exactly what came out (a few kB), so even "No limit" and "Forever" are fine on the Pi's memory card.</p>
    </>
  );
}

function DisplayPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  return (
    <>
      <Topbar title="Display" back={back} />
      <div class="glass grp">
        <ToggleRow label="Reduce motion" sub="Fewer animations, including the print moment." checked={s.display.reduce_motion} onChange={(v) => patch({ display: { reduce_motion: v } })} />
        <ToggleRow label="Reduce transparency" sub="Solid panels instead of frosted glass." checked={s.display.reduce_transparency} onChange={(v) => patch({ display: { reduce_transparency: v } })} />
      </div>
    </>
  );
}

// -------------------------------------------------------------- Connections --
function WeatherPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [place, setPlace] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (s?.weather.lat != null) get<any>("/api/sources/weather").then(setNow).catch(() => {}); }, [s?.weather.lat]);
  if (!s) return null;
  const save = async (e: Event) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await send("POST", "/api/sources/weather/place", { place });
      settings.value = await api.settings();
      setPlace("");
      toast("Place saved");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const f = now?.forecast;
  return (
    <>
      <Topbar title="Weather" back={back} />
      {s.weather.place && (
        <div class="glass grp">
          <div class="lrow kv-row"><span class="grow">Place</span><span class="meta">{s.weather.place}</span></div>
          {f && <div class="lrow kv-row"><span class="grow">Now</span><span class="meta">{Math.round(f.now_temp)}°{s.weather.units} · {f.now_text}</span></div>}
          {now && !f && <div class="lrow"><span class="grow" style="color:var(--c-pink)">Can't reach the weather service.</span></div>}
        </div>
      )}
      <form onSubmit={save} class="glass card" style="margin-top:12px">
        {err && <Banner>{err}</Banner>}
        <label class="field-label" for="place" style="margin-top:0">{s.weather.place ? "Change place" : "Your town or city"}</label>
        <input id="place" class="input" value={place} onInput={(e) => setPlace((e.target as HTMLInputElement).value)} placeholder="e.g. Leeds" />
        <button class="btn btn-green block" style="margin-top:12px" disabled={busy || place.trim().length < 2}>{busy ? "Looking it up…" : "Save place"}</button>
      </form>
      <label class="field-label">Units</label>
      <Seg label="Units" value={s.weather.units} onChange={(v) => patch({ weather: { units: v } })} options={[{ value: "C", label: "°C" }, { value: "F", label: "°F" }]} />
      <p class="dim tiny" style="margin:12px 6px">Forecasts come from Open-Meteo (free, no account). If it can't be reached, prints use the last forecast from the past 3 hours, or say "Weather unavailable".</p>
    </>
  );
}

// ----------------------------------------------------------------- Google --
// One Google sign-in for Calendar and Tasks (backend sources/google.py, docs/GOOGLE_SETUP.md).
// Google only lets this kind of app return to a loopback address, so the sign-in ends on a page
// that "can't be reached" and the person copies its address back here.
interface GoogleStatus {
  client: boolean; connected: boolean; email: string | null; client_id_hint: string; redirect_uri: string;
  health: Record<string, { ok: boolean; message?: string; reauth?: boolean }>;
  settings: { calendars: { id: string; name: string }[]; task_lists: string[] };
}
export const googleState = signal<GoogleStatus | null>(null);
let googleLoading = false;
export function loadGoogle() {
  if (googleLoading) return Promise.resolve();
  googleLoading = true;
  return get<GoogleStatus>("/api/google").then((g) => { googleState.value = g; }).catch(() => {}).finally(() => { googleLoading = false; });
}
function googleMeta() {
  if (!googleState.value) loadGoogle();
  const g = googleState.value;
  if (!g) return "";
  if (Object.values(g.health ?? {}).some((h) => h.reauth)) return "Sign in again";
  return g.connected ? (g.email ?? "Connected") : "Not connected";
}

const PAGES_HOME = "https://keyquesttech.github.io/Wall-of-text/";

function GoogleSetupSteps() {
  const [kind, setKind] = useState<"external" | "internal">("external");
  return (
    <div class="stack">
      <Seg small label="Google account type" value={kind} onChange={setKind}
        options={[{ value: "external", label: "Gmail account" }, { value: "internal", label: "Workspace account" }]} />
      <ol class="small steps">
        <li>On a computer, open <span class="mono">console.cloud.google.com</span>{kind === "internal" ? <> signed in with your <b>work</b> account</> : null} and create a project (it's free).</li>
        <li>In <b>APIs &amp; Services › Library</b>, turn on <b>Google Calendar API</b> and <b>Google Tasks API</b>.</li>
        {kind === "external" ? (
          <li>In <b>OAuth consent screen</b>, choose <b>External</b>. On <b>Branding</b>, enter the home page <span class="mono">{PAGES_HOME}</span>, the privacy policy <span class="mono">{PAGES_HOME}privacy.html</span> and the authorized domain <span class="mono">keyquesttech.github.io</span>. Add your Gmail address as a test user, then <b>Publish app</b> and <b>Confirm</b>. Left in "Testing", Google ends the sign-in after 7 days.</li>
        ) : (
          <li>In <b>OAuth consent screen</b>, choose <b>Internal</b> and enter an app name and your email. Nothing else is needed: no home page, no publishing, no 7-day limit. Only accounts in your organisation can sign in.</li>
        )}
        <li>In <b>Credentials › Create credentials › OAuth client ID</b>, choose <b>Desktop app</b>.</li>
        <li>Copy the <b>Client ID</b> and <b>Client secret</b> into the boxes below.</li>
      </ol>
    </div>
  );
}

function GooglePage() {
  const back = useBack();
  const [, patch] = useSettings();
  const g = googleState.value;
  const [cid, setCid] = useState(""), [sec, setSec] = useState("");
  const [editClient, setEditClient] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cals, setCals] = useState<{ id: string; name: string; primary: boolean }[] | null>(null);
  const [lists, setLists] = useState<{ id: string; title: string }[] | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);
  useEffect(() => { loadGoogle(); }, []);
  const needsClient = !!g && (!g.client || editClient);
  const needsSignIn = !!g && g.client && !g.connected && !editClient;
  useEffect(() => { // get the Google address ready, so the button is a plain link (no pop-up blocker)
    if (!needsSignIn) return;
    send<{ url: string }>("POST", "/api/google/start").then((r) => setAuthUrl(r.url)).catch((e) => setErr(e.message));
  }, [needsSignIn]);
  useEffect(() => {
    if (!g?.connected) return;
    setListErr(null);
    get<{ items: any[] }>("/api/google/calendars").then((r) => setCals(r.items)).catch((e) => setListErr(e.message));
    get<{ items: any[] }>("/api/google/tasklists").then((r) => setLists(r.items)).catch((e) => setListErr(e.message));
  }, [g?.connected, g?.email]);

  const saveClient = async (e: Event) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await send("PUT", "/api/google/client", { client_id: cid.trim(), client_secret: sec.trim() }); setCid(""); setSec(""); setEditClient(false); await loadGoogle(); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const finish = async (e: Event) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await send<{ email: string | null; missing: string[] }>("POST", "/api/google/finish", { response: pasted.trim() });
      setPasted("");
      toast(r.missing.length ? `Connected, but without ${r.missing.join(" and ")}. Sign in again and tick every box.` : `Connected${r.email ? ` as ${r.email}` : ""}`);
      await loadGoogle();
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const disconnect = async (forgetClient: boolean) => {
    await send("DELETE", `/api/google${forgetClient ? "?forget_client=true" : ""}`);
    setConfirmOff(false); setCals(null); setLists(null); setAuthUrl(null);
    await loadGoogle();
    toast(forgetClient ? "Google project removed" : "Disconnected from Google");
  };

  if (!g) return (<><Topbar title="Google" back={back} /><div class="shim" style="height:180px" /></>);
  const chosenCals = g.settings.calendars ?? [];
  const primary = cals?.find((c) => c.primary);
  const calOn = (id: string) => (chosenCals.length ? chosenCals.some((c) => c.id === id) : id === primary?.id);
  const setCal = async (c: { id: string; name: string }, on: boolean) => {
    const cur = chosenCals.length ? chosenCals : primary ? [{ id: primary.id, name: primary.name }] : [];
    const next = on ? [...cur.filter((x) => x.id !== c.id), { id: c.id, name: c.name }] : cur.filter((x) => x.id !== c.id);
    if (!next.length) { toast("Keep at least one calendar on."); return; }
    await patch({ google: { calendars: next } });
    await loadGoogle();
  };
  const chosenLists = g.settings.task_lists ?? [];
  const listOn = (id: string) => (chosenLists.length ? chosenLists.includes(id) : id === lists?.[0]?.id);
  const setList = async (id: string, on: boolean) => {
    const cur = chosenLists.length ? chosenLists : lists?.[0] ? [lists[0].id] : [];
    const next = on ? [...cur.filter((x) => x !== id), id] : cur.filter((x) => x !== id);
    if (!next.length) { toast("Keep at least one list on."); return; }
    await patch({ google: { task_lists: next } });
    await loadGoogle();
  };
  const reauth = Object.values(g.health ?? {}).find((h) => h.reauth);

  return (
    <>
      <Topbar title="Google" back={back} />
      <p class="cap" style="margin:-4px 4px 0">Your calendars and tasks, read straight from Google. Wall of Text can only read them, never change them.</p>
      {reauth && g.connected && (
        <Banner action={<button class="btn small" onClick={() => disconnect(false)}>Sign in again</button>}>{reauth.message ?? "Google stopped accepting the sign-in."}</Banner>
      )}
      {err && <Banner>{err}</Banner>}

      {needsClient && (
        <>
          <h2 class="section">Step 1 of 2 · Your Google project</h2>
          <div class="glass card stack">
            <p style="margin:0">Google needs a free project of your own before an app like this can read your calendar and tasks. It takes about 10 minutes, once.</p>
            <GoogleSetupSteps />
            <form class="stack" onSubmit={saveClient}>
              <div>
                <label class="field-label" for="gcid">Client ID</label>
                <input id="gcid" class="input" value={cid} autoComplete="off" spellcheck={false} placeholder="1234…apps.googleusercontent.com" onInput={(e) => setCid((e.target as HTMLInputElement).value)} />
              </div>
              <div>
                <label class="field-label" for="gsec">Client secret</label>
                <input id="gsec" class="input" type="password" value={sec} autoComplete="off" spellcheck={false} placeholder="GOCSPX-…" onInput={(e) => setSec((e.target as HTMLInputElement).value)} />
              </div>
              <div class="row">
                {editClient && <button type="button" class="btn grow" onClick={() => setEditClient(false)}>Cancel</button>}
                <button class="btn-green grow" disabled={busy || cid.trim().length < 20 || sec.trim().length < 10}>{busy ? "Saving…" : "Save and continue"}</button>
              </div>
            </form>
          </div>
        </>
      )}

      {needsSignIn && (
        <>
          <h2 class="section">Step 2 of 2 · Sign in</h2>
          <div class="glass card stack">
            <ol class="small steps">
              <li>Tap <b>Sign in with Google</b> and choose your account (with an Internal project, your work account). If Google says the app isn't verified, tap <b>Advanced › Go to … (unsafe)</b>: it's your own project.</li>
              <li>Tick the boxes for Calendar and Tasks, then tap <b>Continue</b>.</li>
              <li>The next page says it <b>can't be reached</b>. That's expected. Copy the whole address from the address bar (it starts <span class="mono">{g.redirect_uri}</span>).</li>
              <li>Come back to this tab and paste it below.</li>
            </ol>
            <a class={`btn-green block ${authUrl ? "" : "disabled"}`} href={authUrl ?? undefined} target="_blank" rel="noopener noreferrer"
              aria-disabled={!authUrl} onClick={(e) => { if (!authUrl) e.preventDefault(); }}>Sign in with Google</a>
            <form class="stack" onSubmit={finish}>
              <div>
                <label class="field-label" for="gpaste">Address of the page Google opened</label>
                <textarea id="gpaste" class="input" style="min-height:84px" value={pasted} spellcheck={false} autoComplete="off"
                  placeholder={`${g.redirect_uri}?state=…&code=…`} onInput={(e) => setPasted((e.target as HTMLTextAreaElement).value)} />
              </div>
              <button class="btn-green block" disabled={busy || pasted.trim().length < 10}>{busy ? "Connecting…" : "Connect"}</button>
            </form>
            <button class="btn btn-ghost block" onClick={() => setEditClient(true)}>Use a different client ID</button>
          </div>
        </>
      )}

      {g.connected && !editClient && (
        <>
          <div class="glass tg card row" style="gap:12px">
            <span class="ico g"><IconCalendar class="i" /></span>
            <div class="grow"><div class="h3">Connected</div><div class="cap" style="overflow-wrap:anywhere">{g.email ?? "Google account"}</div></div>
          </div>
          {listErr && <Banner>{listErr}</Banner>}
          <h2 class="section">Calendars to print</h2>
          <div class="glass grp">
            {cals === null && !listErr && <div class="lrow"><div class="shim grow" style="height:20px" /></div>}
            {cals?.map((c) => (
              <div class="lrow"><span class="grow">{c.name}{c.primary && <span class="cap"> · main</span>}</span>
                <Toggle label={`Print ${c.name}`} checked={calOn(c.id)} onChange={(v) => setCal(c, v)} />
              </div>
            ))}
          </div>
          <h2 class="section">Task lists to print</h2>
          <div class="glass grp">
            {lists === null && !listErr && <div class="lrow"><div class="shim grow" style="height:20px" /></div>}
            {lists?.length === 0 && <div class="lrow dim">No task lists in this account.</div>}
            {lists?.map((l) => (
              <div class="lrow"><span class="grow">{l.title}</span>
                <Toggle label={`Print ${l.title}`} checked={listOn(l.id)} onChange={(v) => setList(l.id, v)} />
              </div>
            ))}
          </div>
          <button class="btn btn-danger block" onClick={() => setConfirmOff(true)}>Disconnect Google</button>
        </>
      )}
      {g.client && !needsClient && (
        <p class="dim tiny" style="margin:4px 6px">Google project: <span class="mono">{g.client_id_hint}</span></p>
      )}
      <Sheet open={confirmOff} onClose={() => setConfirmOff(false)} title="Disconnect Google?">
        <p>Schedules with your calendar or tasks will print "Google isn't connected" until you sign in again.</p>
        <div class="stack" style="margin-top:12px">
          <button class="btn btn-danger block" onClick={() => disconnect(false)}>Disconnect</button>
          <button class="btn block" onClick={() => disconnect(true)}>Disconnect and remove the project</button>
        </div>
      </Sheet>
    </>
  );
}

// --------------------------------------------------------------- Fortunes --
function FortunesPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [info, setInfo] = useState<{ builtin_count: number; custom_count: number; use_builtin: boolean; in_play: number; sample: string[] } | null>(null);
  const [mode, setMode] = useState<"replace" | "add">("replace");
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const load = () => get<any>("/api/fortunes").then(setInfo);
  useEffect(() => { load(); }, []);
  const onFile = async () => {
    const f = file.current?.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    fd.append("mode", mode);
    setBusy(true);
    try {
      const r = await upload<any>("/api/fortunes/csv", fd);
      setInfo(r);
      toast(`${r.added} fortune${r.added === 1 ? "" : "s"} added${r.skipped ? `, ${r.skipped} skipped (empty, repeated or over 300 characters)` : ""}`);
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); if (file.current) file.current.value = ""; }
  };
  if (!s || !info) return (<><Topbar title="Fortunes" back={back} /><div class="shim" style="height:160px" /></>);
  return (
    <>
      <Topbar title="Fortunes" back={back} />
      <div class="glass grp">
        <div class="lrow kv-row"><span class="grow">In use</span><span class="meta">{info.in_play} fortunes</span></div>
        <div class="lrow kv-row"><span class="grow">Yours</span><span class="meta">{info.custom_count}</span></div>
        <ToggleRow label="Use the built-in fortunes too" sub={`${info.builtin_count} short lines that come with the printer. Always used while you have none of your own.`}
          checked={s.fortunes?.use_builtin ?? true} onChange={(v) => patch({ fortunes: { use_builtin: v } }).then(load)} />
      </div>
      <h2 class="section">Upload a CSV</h2>
      <div class="glass card stack">
        <p class="small" style="margin:0">One fortune per row, in the first column (or a column headed <span class="mono">fortune</span>). Export it from Excel, Numbers or Google Sheets as CSV, or use a plain text file with one per line.</p>
        <Seg label="When uploading" value={mode} onChange={setMode}
          options={[{ value: "replace", label: "Replace mine" }, { value: "add", label: "Add to mine" }]} />
        <input id="fcsv" ref={file} type="file" accept=".csv,.txt,text/csv,text/plain" class="sr-only" onChange={onFile} />
        <label for="fcsv" class={`btn-green block ${busy ? "disabled" : ""}`}>{busy ? "Uploading…" : "Choose a CSV file"}</label>
        <div class="row">
          <a class="btn grow" href="/api/fortunes/csv" download="walloftext-fortunes.csv">Download as CSV</a>
          {info.custom_count > 0 && <button class="btn btn-danger grow" onClick={() => send<any>("DELETE", "/api/fortunes/custom").then((r) => { setInfo(r); toast("Your fortunes were removed"); })}>Remove mine</button>}
        </div>
      </div>
      {info.sample.length > 0 && (
        <>
          <h2 class="section">First of yours</h2>
          <div class="glass grp">{info.sample.map((x) => <div class="lrow"><span class="grow" style="white-space:normal">{x}</span></div>)}</div>
        </>
      )}
      <p class="dim tiny" style="margin:8px 6px">Fortunes are picked at random, but each one prints once before any comes back, and the ones from the last week are held back when a new round starts.</p>
    </>
  );
}

// ----------------------------------------------------------- Telegram bot --
// Backend remote/bot.py. Commands, templates to copy, and asking how each message prints.
const TG_STYLES: [string, string][] = [["message", "Message slip"], ["plain", "Plain text"], ["big", "Big text"], ["checklist", "Checklist"]];
const TG_BUILTINS: [string, string][] = [["help", "What the bot can do"], ["settings", "How your messages print (buttons)"],
  ["templates", "Get a template back to copy"], ["cancel", "Don't print the message waiting for a choice"]];
const CMD_RE = /^[a-z0-9_]{1,32}$/;

function TelegramPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [actions, setActions] = useState<{ id: string; label: string }[]>([]);
  const [draft, setDraft] = useState<any[] | null>(null); // commands being edited (saved on blur)
  const [tdraft, setTdraft] = useState<any[] | null>(null);
  useEffect(() => { get<{ id: string; label: string }[]>("/api/actions").then((a) => setActions(a.filter((x) => x.id !== "none"))).catch(() => {}); }, []);
  if (!s) return null;
  const t = s.telegram;
  const cmds: any[] = draft ?? t.commands ?? [];
  const tpls: any[] = tdraft ?? t.templates ?? [];
  // keep the edited copy until the save has come back, so typing straight on isn't lost
  const saveCmds = (xs: any[]) => { setDraft(xs); patch({ telegram: { commands: xs } }).finally(() => setDraft((cur) => (cur === xs ? null : cur))); };
  const saveTpls = (xs: any[]) => { setTdraft(xs); patch({ telegram: { templates: xs } }).finally(() => setTdraft((cur) => (cur === xs ? null : cur))); };
  const setCmd = (i: number, p: any, save = false) => { const xs = cmds.map((c, k) => (k === i ? { ...c, ...p } : c)); save ? saveCmds(xs) : setDraft(xs); };
  const setTpl = (i: number, p: any, save = false) => { const xs = tpls.map((c, k) => (k === i ? { ...c, ...p } : c)); save ? saveTpls(xs) : setTdraft(xs); };
  const names = cmds.map((c) => String(c.name || "").replace(/^\//, "").toLowerCase());
  const cmdProblem = (i: number) => {
    const n = names[i];
    if (!n) return "Give it a name.";
    if (!CMD_RE.test(n)) return "Use lowercase letters, digits and _ only (up to 32).";
    if (TG_BUILTINS.some(([b]) => b === n) || n === "start") return `/${n} is built in.`;
    if (names.indexOf(n) !== i) return `/${n} is used twice.`;
    return null;
  };
  const d = t.defaults ?? { style: "message", size: "M" };
  return (
    <>
      <Topbar title="Telegram" back={back} />
      <p class="cap" style="margin:-4px 4px 0">Message the printer from Telegram. Everything for the bot is here: connection, people, how messages print, commands and templates.</p>
      <TelegramConnection />

      <h2 class="section">How messages print</h2>
      <div class="glass grp">
        <div class="lrow"><label for="tgstyle" style="flex:none">Style</label>
          <select id="tgstyle" class="input" style="flex:1;min-width:0;max-width:220px;margin-left:auto" value={d.style} onChange={(e) => patch({ telegram: { defaults: { style: (e.target as HTMLSelectElement).value } } })}>
            {TG_STYLES.map(([v, l]) => <option value={v}>{l}</option>)}
          </select></div>
        <div class="lrow col"><span>Text size</span>
          <Seg label="Text size" value={d.size} onChange={(v) => patch({ telegram: { defaults: { size: v } } })}
            options={["S", "M", "L", "XL"].map((v) => ({ value: v, label: v }))} /></div>
        <ToggleRow label="Ask how to print each message" sub="The bot answers with buttons for the style and size, then Print or Cancel." checked={!!t.ask_options}
          onChange={(v) => patch({ telegram: { ask_options: v } })} />
        {t.ask_options && (
          <>
            <div class="lrow"><label for="tgwait" class="grow">If there's no answer in</label>
              <select id="tgwait" class="input" style="width:auto" value={String(t.ask_timeout_s)} onChange={(e) => patch({ telegram: { ask_timeout_s: Number((e.target as HTMLSelectElement).value) } })}>
                {[60, 120, 300, 600, 1800].map((v) => <option value={String(v)}>{v / 60} min</option>)}
              </select></div>
            <div class="lrow col"><span>then</span>
              <Seg label="When there's no answer" value={t.on_timeout} onChange={(v) => patch({ telegram: { on_timeout: v } })}
                options={[{ value: "print", label: "Print it anyway" }, { value: "cancel", label: "Don't print" }]} /></div>
          </>
        )}
      </div>
      <p class="dim tiny" style="margin:8px 6px">Each person can change their own style and size with /settings. Big text and Checklist work best for short messages; Checklist puts a box before every line.</p>

      <h2 class="section">Commands</h2>
      <p class="dim tiny" style="margin:0 6px 8px">Type “/” in the chat with the bot to see them.</p>
      <div class="glass grp">
        {TG_BUILTINS.map(([n, desc]) => <div class="lrow"><span class="mono" style="flex:none;color:var(--hi)">/{n}</span><span class="grow sub" style="white-space:normal;text-align:right">{desc}</span></div>)}
      </div>

      <span class="sect" style="margin-top:8px">Your commands</span>
      {cmds.map((c, i) => {
        const prob = cmdProblem(i);
        return (
          <div class="glass grp">
            <div class="lrow">
              <span class="mono" style="flex:none;color:var(--hi)">/</span>
              <label class="sr-only" for={`cn${i}`}>Command name</label>
              <input id={`cn${i}`} class="input mono grow" value={c.name} maxLength={33} placeholder="name" autoCapitalize="none" spellcheck={false}
                onInput={(e) => setCmd(i, { name: (e.target as HTMLInputElement).value.replace(/^\//, "").toLowerCase() })} onBlur={() => saveCmds(cmds)} />
              <button class="ib" aria-label={`Remove /${c.name || "command"}`} onClick={() => saveCmds(cmds.filter((_, k) => k !== i))}><IconTrash class="i" /></button>
            </div>
            {prob && <div class="lrow"><span class="cap" style="color:var(--pink-text)">{prob}</span></div>}
            <div class="lrow">
              <label class="sr-only" for={`cd${i}`}>Description</label>
              <input id={`cd${i}`} class="input grow" value={c.description ?? ""} maxLength={80} placeholder="What it does (shown in the / menu)"
                onInput={(e) => setCmd(i, { description: (e.target as HTMLInputElement).value })} onBlur={() => saveCmds(cmds)} />
            </div>
            <div class="lrow"><label for={`ct${i}`} style="flex:none">It should</label>
              <select id={`ct${i}`} class="input" style="flex:1;min-width:0;max-width:240px;margin-left:auto" value={c.type} onChange={(e) => setCmd(i, { type: (e.target as HTMLSelectElement).value }, true)}>
                <option value="reply">Reply with text</option>
                <option value="action">Print something</option>
                <option value="style">Set how the next message prints</option>
              </select></div>
            {c.type === "reply" && (
              <>
                <div class="lrow col">
                  <label class="sr-only" for={`cr${i}`}>Reply</label>
                  <textarea id={`cr${i}`} class="input" style="min-height:80px" maxLength={3500} placeholder="What the bot sends back" value={c.text ?? ""}
                    onInput={(e) => setCmd(i, { text: (e.target as HTMLTextAreaElement).value })} onBlur={() => saveCmds(cmds)} />
                </div>
                <ToggleRow label="Send as a block to copy" sub="One tap copies it in Telegram." checked={!!c.copyable} onChange={(v) => setCmd(i, { copyable: v }, true)} />
              </>
            )}
            {c.type === "action" && (
              <div class="lrow"><label for={`ca${i}`} style="flex:none">Print</label>
                <select id={`ca${i}`} class="input" style="flex:1;min-width:0;max-width:240px;margin-left:auto" value={c.action ?? ""} onChange={(e) => setCmd(i, { action: (e.target as HTMLSelectElement).value }, true)}>
                  <option value="" disabled>Choose…</option>
                  {actions.map((a) => <option value={a.id}>{a.label.replace("Run routine: ", "Routine: ")}</option>)}
                </select></div>
            )}
            {c.type === "style" && (
              <>
                <div class="lrow"><label for={`cs${i}`} style="flex:none">Style</label>
                  <select id={`cs${i}`} class="input" style="flex:1;min-width:0;max-width:220px;margin-left:auto" value={c.style ?? "big"} onChange={(e) => setCmd(i, { style: (e.target as HTMLSelectElement).value }, true)}>
                    {TG_STYLES.map(([v, l]) => <option value={v}>{l}</option>)}
                  </select></div>
                <div class="lrow col"><span>Text size</span>
                  <Seg label={`/${c.name} text size`} value={c.size ?? "M"} onChange={(v) => setCmd(i, { size: v }, true)}
                    options={["S", "M", "L", "XL"].map((v) => ({ value: v, label: v }))} /></div>
                <div class="lrow"><span class="cap">“/{c.name || "name"} Hello” prints “Hello” now; “/{c.name || "name"}” on its own applies to the next message.</span></div>
              </>
            )}
          </div>
        );
      })}
      <button class="add-row" onClick={() => saveCmds([...cmds, { name: "", description: "", type: "reply", text: "", copyable: false }])}><IconPlus class="i" width={18} />Add a command</button>

      <h2 class="section">Templates</h2>
      <p class="dim tiny" style="margin:0 6px 8px">/templates shows these as buttons. Tapping one sends its text back as a block to copy, fill in and send.</p>
      {tpls.map((tp, i) => (
        <div class="glass grp">
          <div class="lrow">
            <label class="sr-only" for={`tn${i}`}>Template name</label>
            <input id={`tn${i}`} class="input grow" value={tp.name ?? ""} maxLength={40} placeholder="Name (the button)"
              onInput={(e) => setTpl(i, { name: (e.target as HTMLInputElement).value })} onBlur={() => saveTpls(tpls)} />
            <button class="ib" aria-label={`Remove template ${tp.name || i + 1}`} onClick={() => saveTpls(tpls.filter((_, k) => k !== i))}><IconTrash class="i" /></button>
          </div>
          <div class="lrow col">
            <label class="sr-only" for={`tt${i}`}>Template text</label>
            <textarea id={`tt${i}`} class="input mono" style="min-height:90px" maxLength={3500} value={tp.text ?? ""}
              onInput={(e) => setTpl(i, { text: (e.target as HTMLTextAreaElement).value })} onBlur={() => saveTpls(tpls)} />
          </div>
        </div>
      ))}
      <button class="add-row" onClick={() => saveTpls([...tpls, { name: "", text: "" }])}><IconPlus class="i" width={18} />Add a template</button>
      <TelegramRemove />
    </>
  );
}

// ------------------------------------------------------------ Date & time --
interface TimeState { epoch: number; timezone: string; system_timezone: string; ntp: boolean; synced: boolean; manual_this_boot: boolean; scheduler_waiting: boolean }
const fmtTime = (epoch: number, tz: string) => {
  try { return new Date(epoch * 1000).toLocaleString("en-GB", { timeZone: tz, weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
  catch { return new Date(epoch * 1000).toLocaleString(); }
};
const pad = (n: number) => String(n).padStart(2, "0");

function TimePage() {
  const back = useBack();
  const [t, setT] = useState<TimeState | null>(null);
  const [skew, setSkew] = useState(0); // Pi clock minus this device's clock, in seconds
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState({ date: "", time: "" });
  const apply = (x: TimeState) => { setT(x); setSkew(x.epoch - Date.now() / 1000); };
  useEffect(() => { get<TimeState>("/api/device/time").then(apply).catch(() => {}); const i = setInterval(() => setTick((k) => k + 1), 1000); return () => clearInterval(i); }, []);
  useEffect(() => {
    if (!t) return;
    const d = new Date(Date.now() + skew * 1000);
    setManual({ date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` });
  }, [t?.ntp]);
  const put = async (body: any, msg: string) => {
    setBusy(true);
    try { apply(await send<TimeState>("PUT", "/api/device/time", body)); settings.value = await api.settings(); toast(msg); }
    catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  if (!t) return (<><Topbar title="Date & time" back={back} /><div class="shim" style="height:160px" /></>);
  const piNow = Date.now() / 1000 + skew;
  void tick;
  const off = Math.round(skew);
  const zones = ((Intl as any).supportedValuesOf?.("timeZone") as string[] | undefined) ?? ["Europe/London", "Europe/Dublin", "Europe/Madrid", "Europe/Paris", "America/New_York", "UTC"];
  return (
    <>
      <Topbar title="Date & time" back={back} />
      <div class={`glass card ${t.synced || t.manual_this_boot ? "tg" : ""}`}>
        <div class="lbl">The printer's clock</div>
        <div class="h2 num" style="margin:4px 0">{fmtTime(piNow, t.timezone)}</div>
        <div class="cap">{t.ntp ? (t.synced ? "Set automatically from the internet." : "Waiting for the internet to set it…") : t.manual_this_boot ? "Set by hand." : "Not set since the last power cut."}
          {Math.abs(off) >= 60 && ` ${Math.abs(off) >= 3600 ? `${Math.round(Math.abs(off) / 3600)} h` : `${Math.round(Math.abs(off) / 60)} min`} ${off > 0 ? "ahead of" : "behind"} this device.`}</div>
      </div>
      {t.scheduler_waiting && <Banner>Schedules are waiting for the clock. Set it by hand below, or connect the printer to the internet.</Banner>}
      <div class="glass grp">
        <ToggleRow label="Set automatically" sub="From internet time servers. Best when the printer is online." checked={t.ntp}
          onChange={(v) => (v ? put({ auto: true }, "Clock set automatically") : put({ epoch_ms: Date.now() }, "Clock set from this device"))} />
      </div>
      {!t.ntp && (
        <>
          <h2 class="section">Set by hand</h2>
          <div class="glass card stack">
            <button class="btn-green block" disabled={busy} onClick={() => put({ epoch_ms: Date.now() }, "Clock set from this device")}>Use this device's time</button>
            <div class="row">
              <label class="sr-only" for="tdate">Date</label>
              <input id="tdate" type="date" class="input grow" value={manual.date} onInput={(e) => setManual({ ...manual, date: (e.target as HTMLInputElement).value })} />
              <label class="sr-only" for="ttime">Time</label>
              <input id="ttime" type="time" class="input" style="width:130px" value={manual.time} onInput={(e) => setManual({ ...manual, time: (e.target as HTMLInputElement).value })} />
            </div>
            <button class="btn block" disabled={busy || !manual.date || !manual.time} onClick={() => put({ epoch_ms: new Date(`${manual.date}T${manual.time}:00`).getTime() }, "Clock set")}>Set this date and time</button>
            <p class="cap" style="margin:0">The date and time are read in this device's time zone. The printer has no battery clock, so after a power cut it needs setting again (or the internet).</p>
          </div>
        </>
      )}
      <h2 class="section">Time zone</h2>
      <div class="glass card">
        <select class="input" value={t.timezone} aria-label="Time zone" disabled={busy} onChange={(e) => put({ timezone: (e.target as HTMLSelectElement).value }, "Time zone saved")}>
          {(zones.includes(t.timezone) ? zones : [t.timezone, ...zones]).map((z) => <option value={z}>{z.replace(/_/g, " ")}</option>)}
        </select>
        <p class="cap" style="margin:8px 4px 0">Schedules, quiet hours and the time on prints use this zone.</p>
      </div>
    </>
  );
}

// ----------------------------------------------------------- Guest & inbox --
/** Guest notes and remote messages that need a yes before they print. */
function InboxPage() {
  const back = useBack();
  const [items, setItems] = useState<any[] | null>(null);
  const load = () => get<{ items: any[] }>("/api/inbox").then((r) => setItems(r.items));
  useEffect(() => { load(); }, [inboxWaiting.value]);
  return (
    <>
      <Topbar title="Waiting for your OK" back={back} />
      {items === null ? <div class="shim" style="height:60px" /> : <div class="glass grp">
        {items.length === 0 && <div class="lrow dim">Nothing waiting.</div>}
        {items.map((i) => (
          <div class="lrow" style="flex-wrap:wrap">
            <div class="grow">
              <div class="title">{i.sender} · {i.source === "Guest" ? "Guest page" : `via ${i.channel}`}</div>
              <div class="sub" style="white-space:normal">{i.preview || "(sticker)"} · {timeAgo(i.created_at)}</div>
            </div>
            <div class="row">
              <button class="btn small" onClick={() => send("POST", `/api/inbox/${i.id}/decline`).then(load)}>Decline</button>
              <button class="btn small btn-green" onClick={() => send("POST", `/api/inbox/${i.id}/approve`).then(() => { toast("Printing"); load(); })}>Print it</button>
            </div>
          </div>
        ))}
      </div>}
      <p class="dim tiny" style="margin:8px 6px">Guest notes (when the guest page waits for your OK) and remote messages from senders you haven't allowed to print straight away land here.
        Set them up in <a href="/settings/guest" style="color:var(--green);text-decoration:underline">Guest page</a>, <a href="/settings/email" style="color:var(--green);text-decoration:underline">Email</a> and <a href="/settings/telegram" style="color:var(--green);text-decoration:underline">Telegram</a>.</p>
    </>
  );
}

function GuestPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  if (!s) return null;
  const g = s.guest;
  return (
    <>
      <Topbar title="Guest page" back={back} />
      <div class="glass grp">
        <ToggleRow label="Guest page" sub={`Visitors on your Wi-Fi can leave a note at ${wifi.value?.hostname ?? "walloftext.local"}/note, no password needed.`} checked={g.enabled}
          onChange={(v) => patch({ guest: { enabled: v } })} />
        {g.enabled && (
          <>
            <div class="lrow"><span class="grow">Notes</span>
              <Seg label="Guest notes" value={g.mode} onChange={(v) => patch({ guest: { mode: v } })}
                options={[{ value: "approve", label: "Wait for my OK" }, { value: "print", label: "Print straight away" }]} />
            </div>
            <div class="lrow"><span class="grow">Longest note</span>
              <select class="input" style="width:auto" value={g.max_chars} aria-label="Longest note" onChange={(e) => patch({ guest: { max_chars: Number((e.target as HTMLSelectElement).value) } })}>
                {[140, 280, 500, 1000].map((n) => <option value={n}>{n} characters</option>)}
              </select>
            </div>
          </>
        )}
      </div>
    </>
  );
}

// ------------------------------------------------------------------ Device --
// ------------------------------------------------------------- USB backup --
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function UsbBackupGroup() {
  const [s, patch] = useSettings();
  const [st, setSt] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const load = () => get<any>("/api/backup/usb").then(setSt).catch(() => {});
  useEffect(() => { load(); const t = window.setInterval(load, 10000); return () => window.clearInterval(t); }, []);
  if (!s) return null;
  const b = s.backup ?? { usb_enabled: false, frequency: "weekly", time: "03:00", weekday: 6, keep: 10 };
  const set = (v: any) => patch({ backup: v }).then(load);
  const drive = st?.drives?.[0];
  const last = st?.last;
  const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return (
    <>
      <h2 class="section">Backup to USB</h2>
      <div class="glass grp">
        <ToggleRow label="Back up to a USB drive" sub="Saves the same backup to a USB stick plugged into the Pi, on a schedule." checked={b.usb_enabled}
          onChange={(v) => set({ usb_enabled: v })} />
        {b.usb_enabled && (
          <>
            <div class="lrow">
              <span class="grow">How often</span>
              <select class="input" style="width:150px" value={b.frequency} aria-label="How often" onChange={(e) => set({ frequency: (e.target as HTMLSelectElement).value })}>
                <option value="daily">Every day</option>
                <option value="weekly">Every week</option>
                <option value="monthly">Every month (1st)</option>
              </select>
            </div>
            {b.frequency === "weekly" && (
              <div class="lrow">
                <span class="grow">Day</span>
                <select class="input" style="width:150px" value={String(b.weekday)} aria-label="Day of the week" onChange={(e) => set({ weekday: Number((e.target as HTMLSelectElement).value) })}>
                  {WEEKDAYS.map((d, i) => <option value={String(i)}>{d}</option>)}
                </select>
              </div>
            )}
            <div class="lrow">
              <span class="grow">Time</span>
              <input type="time" class="input" style="width:150px" value={b.time} aria-label="Backup time" onChange={(e) => set({ time: (e.target as HTMLInputElement).value })} />
            </div>
            <div class="lrow">
              <div class="grow"><div class="title">Keep</div><div class="sub" style="white-space:normal">Older backups on the drive are deleted.</div></div>
              <input type="number" min={1} max={100} class="input" style="width:90px" value={b.keep} aria-label="Backups to keep"
                onChange={(e) => set({ keep: Math.max(1, Math.min(100, Number((e.target as HTMLInputElement).value) || 10)) })} />
            </div>
          </>
        )}
        <div class="lrow">
          <div class="grow">
            <div class="title">{drive ? `Drive: ${drive.label}` : "No USB drive plugged in"}</div>
            <div class="sub" style="white-space:normal">
              {last ? `${last.ok ? "Last backup" : "Last try"} ${timeAgo(last.at)}: ${last.message}` : "No USB backup yet."}
              {b.usb_enabled && st?.next ? ` Next: ${when(st.next)}.` : ""}
            </div>
          </div>
          <button class="btn" disabled={busy || !drive} onClick={async () => {
            setBusy(true);
            try { const r = await send<any>("POST", "/api/backup/usb/run"); toast(r.ok ? "Backed up to USB" : r.message); load(); }
            catch (e) { toast((e as Error).message); } finally { setBusy(false); }
          }}>{busy ? "Saving…" : "Back up now"}</button>
        </div>
      </div>
      <p class="dim tiny" style="margin:8px 6px">Backups go in a WallOfText-backups folder. The drive is safe to unplug once the backup is done.</p>
    </>
  );
}

/** Restart on a schedule (backend restarts.py). */
function RestartGroup(props: { next: string | null; last: { at: number; ok: boolean; message: string } | null }) {
  const [s, patch] = useSettings();
  if (!s) return null;
  const r = s.restart ?? { enabled: false, frequency: "weekly", weekday: 6, time: "04:00" };
  const next = props.next ? new Date(props.next).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : null;
  return (
    <>
      <h2 class="section">Scheduled restart</h2>
      <div class="glass grp">
        <ToggleRow label="Restart on a schedule" sub="A fresh start now and then keeps the printer and Wi-Fi reliable." checked={r.enabled}
          onChange={(v) => patch({ restart: { enabled: v } })} />
        {r.enabled && (
          <>
            <div class="lrow col">
              <Seg label="How often" value={r.frequency} onChange={(v) => patch({ restart: { frequency: v } })}
                options={[{ value: "daily", label: "Every day" }, { value: "weekly", label: "Once a week" }]} />
            </div>
            {r.frequency === "weekly" && (
              <div class="lrow"><span style="flex:none">Day</span>
                <select class="input" style="flex:1;min-width:0;max-width:220px;margin-left:auto" aria-label="Restart day" value={String(r.weekday)}
                  onChange={(e) => patch({ restart: { weekday: Number((e.target as HTMLSelectElement).value) } })}>
                  {WEEKDAYS.map((n, i) => <option value={String(i)}>{n}</option>)}
                </select>
              </div>
            )}
            <div class="lrow"><span class="grow">Time</span>
              <input type="time" class="input" style="width:130px" aria-label="Restart time" value={r.time}
                onChange={(e) => patch({ restart: { time: (e.target as HTMLInputElement).value || "04:00" } })} />
            </div>
          </>
        )}
      </div>
      <p class="dim tiny" style="margin:8px 6px">
        {r.enabled && next ? `Next restart: ${next}. ` : ""}It takes about a minute and never interrupts a print: it waits until nothing is printing. If the printer was off or busy for more than 2 hours after the set time, that restart is skipped.
        {props.last ? ` Last: ${props.last.message} (${timeAgo(props.last.at)}).` : ""}
      </p>
    </>
  );
}

// ------------------------------------------------------------------ Backup --
function BackupPage() {
  const back = useBack();
  const [restoring, setRestoring] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const restore = async () => {
    const f = file.current?.files?.[0];
    if (!f) return;
    setRestoring(true);
    const fd = new FormData();
    fd.append("file", f);
    try { const r = await upload<{ restored: string[] }>("/api/backup", fd); toast(`Restored: ${r.restored.join(", ")}`); settings.value = await api.settings(); }
    catch (e) { toast((e as Error).message); } finally { setRestoring(false); if (file.current) file.current.value = ""; }
  };
  return (
    <>
      <Topbar title="Backup" back={back} />
      <div class="glass grp">
        <a class="lrow" href="/api/backup" download>Download a backup</a>
        <label class="lrow" for="restore" style="cursor:pointer">{restoring ? "Restoring…" : "Restore from a backup"}</label>
      </div>
      <input ref={file} id="restore" type="file" accept=".zip,application/zip" class="sr-only" onChange={restore} />
      <p class="dim tiny" style="margin:8px 6px">Backups hold settings, schedules, templates, lists and uploaded fonts. Passwords and connection secrets are never included.</p>
      <UsbBackupGroup />
    </>
  );
}

// ------------------------------------------------------------------ Device --
function DevicePage() {
  const back = useBack();
  const [d, setD] = useState<any>(null);
  const [confirm, setConfirm] = useState<null | "restart" | "shutdown">(null);
  useEffect(() => { api.device().then(setD); const t = setInterval(() => api.device().then(setD), 10000); return () => clearInterval(t); }, []);
  const up = d ? `${Math.floor(d.uptime_s / 86400)}d ${Math.floor((d.uptime_s % 86400) / 3600)}h` : "";
  const hot = d?.temperature_c != null && d.temperature_c >= 75;
  return (
    <>
      <Topbar title="Device" back={back} />
      {hot && <Banner>The printer's computer is running hot ({d.temperature_c.toFixed(0)} °C). Give it some air.</Banner>}
      {d?.throttled?.flags?.some((f: string) => f === "under_voltage") && <Banner>The power supply is too weak right now. Prints and Wi-Fi may be unreliable.</Banner>}
      <div class="glass">
        <dl class="kv">
          <dt>Version</dt><dd>{d?.version}</dd>
          <dt>Temperature</dt><dd>{d?.temperature_c != null ? `${d.temperature_c.toFixed(1)} °C` : "—"}</dd>
          <dt>Throttling</dt><dd>{d ? (d.throttled.flags.filter((f: string) => !f.endsWith("since_boot")).join(", ") || "None") : ""}</dd>
          <dt>Clock</dt><dd>{d ? (d.clock_synced ? "Set" : "Waiting for the clock") : ""}</dd>
          <dt>Running for</dt><dd>{up}</dd>
          <dt>Free space</dt><dd>{d ? `${(d.disk.free / 1e9).toFixed(1)} GB` : ""}</dd>
          <dt>Address</dt><dd class="mono">{d?.hostname}</dd>
          <dt>IP</dt><dd class="mono">{d?.ips?.join(", ")}</dd>
        </dl>
      </div>
      <p class="dim tiny" style="margin:8px 6px">Updates are installed from your computer with deploy.ps1.</p>
      <RestartGroup next={d?.restart?.next ?? null} last={d?.restart?.last ?? null} />
      <h2 class="section">Power</h2>
      <div class="glass grp">
        <button class="lrow" onClick={() => setConfirm("restart")}>Restart</button>
        <button class="lrow btn-danger" style="color:var(--c-pink)" onClick={() => setConfirm("shutdown")}>Shut down</button>
      </div>
      <Sheet open={!!confirm} onClose={() => setConfirm(null)} title={confirm === "restart" ? "Restart the printer?" : "Shut down the printer?"}>
        <p>{confirm === "restart" ? "It's back in about a minute." : "Wait for the green light on the Pi to stop before unplugging. To turn it back on, unplug and plug in the power."}</p>
        <div class="stack">
          <button class="btn btn-pink" onClick={() => send("POST", `/api/device/${confirm}`).then(() => { setConfirm(null); toast(confirm === "restart" ? "Restarting…" : "Shutting down…"); })}>{confirm === "restart" ? "Restart" : "Shut down"}</button>
          <button class="btn" onClick={() => setConfirm(null)}>Cancel</button>
        </div>
      </Sheet>
    </>
  );
}

// Groups, in this order on Settings: what gets printed and how; where content comes from;
// messages from other people; time; the parts wired to the Pi; and the system itself.
const quietMeta = () => { const sc = settings.value?.schedules; return sc ? (sc.holiday_mode ? "Holiday mode" : sc.quiet_hours?.enabled ? `Quiet ${sc.quiet_hours.start}–${sc.quiet_hours.end}` : "") : ""; };
const onOff = (on: boolean | undefined, text: string) => (on === false ? "Off" : text);
export const SETTINGS_PAGES: SettingsPage[] = [
  // Printing
  { id: "printer", Icon: IconPrinter, title: "Printer", group: "Printing", Component: PrinterPage, meta: () => { const p = settings.value?.printer; return p ? `${String(p.speed).replace(/^./, (c: string) => c.toUpperCase())} speed` : ""; } },
  { id: "paper", Icon: IconRoll, title: "Paper roll", group: "Printing", Component: PaperPage, meta: () => `About ${printer.value?.paper_percent ?? 100}% left` },
  { id: "fonts", Icon: IconFont, title: "Fonts", group: "Printing", Component: FontsPage },
  { id: "history", Icon: IconHistory, title: "History", group: "Printing", Component: HistoryPrefs, meta: () => { const h = settings.value?.history; return h ? (h.max_days ? `${h.max_days} days` : "Forever") : ""; } },
  // What it prints
  { id: "weather", Icon: IconCloud, title: "Weather", group: "What it prints", Component: WeatherPage, meta: () => settings.value?.weather?.place || "Not set" },
  { id: "google", Icon: IconCalendar, title: "Google Calendar & Tasks", group: "What it prints", Component: GooglePage, meta: googleMeta },
  { id: "fortunes", Icon: IconStar, title: "Fortunes", group: "What it prints", Component: FortunesPage },
  // Messages
  { id: "inbox", Icon: IconInbox, title: "Waiting for your OK", group: "Messages", Component: InboxPage, meta: () => (inboxWaiting.value ? `${inboxWaiting.value} waiting` : "None") },
  { id: "guest", Icon: IconNote, title: "Guest page", group: "Messages", Component: GuestPage, meta: () => (settings.value?.guest?.enabled ? (settings.value.guest.mode === "print" ? "Prints straight away" : "Waits for your OK") : "Off") },
  { id: "email", Icon: IconMail, title: "Email", group: "Messages", Component: EmailPage },
  { id: "telegram", Icon: IconBot, title: "Telegram", group: "Messages", Component: TelegramPage },
  // Time & schedules
  { id: "schedules", Icon: IconAlarm, title: "Schedules", group: "Time & schedules", Component: SchedulePrefs, meta: quietMeta },
  { id: "time", Icon: IconClock, title: "Date & time", group: "Time & schedules", Component: TimePage, meta: () => settings.value?.schedules?.timezone?.replace(/_/g, " ") ?? "" },
  // Hardware
  { id: "button", Icon: IconButton, title: "Button", group: "Hardware", Component: ButtonPage, meta: () => onOff(settings.value?.button?.enabled, `GPIO${settings.value?.button?.pin ?? 17}`) },
  { id: "light", Icon: IconBulb, title: "Panel light", group: "Hardware", Component: LightPage, meta: () => onOff(settings.value?.led?.enabled, `GPIO${settings.value?.led?.pin ?? 18}`) },
  { id: "fan", Icon: IconFan, title: "Fan", group: "Hardware", Component: FanPage, meta: () => (settings.value?.fan?.enabled ? (settings.value.fan.mode === "always" ? "Always on" : `From ${settings.value.fan.start_temp} °C`) : "Off") },
  { id: "strip", Icon: IconStrip, title: "LED strip", group: "Hardware", Component: StripPage, meta: () => (settings.value?.neopixel?.enabled ? `${(settings.value.neopixel.strips ?? []).reduce((a: number, x: any) => a + (x.count || 0), 0)} LEDs` : "Off") },
  // System
  { id: "wifi", Icon: IconWifi, title: "Wi-Fi", group: "System", Component: WifiPage, meta: () => wifi.value?.ssid ?? "" },
  { id: "access", Icon: IconLock, title: "Passwords & access", group: "System", Component: AccessPage },
  { id: "backup", Icon: IconBackup, title: "Backup", group: "System", Component: BackupPage, meta: () => (settings.value?.backup?.usb_enabled ? "USB on" : "") },
  { id: "device", Icon: IconDevice, title: "Device", group: "System", Component: DevicePage, meta: () => (settings.value?.restart?.enabled ? "Restarts on a schedule" : "") },
  { id: "display", Icon: IconEye, title: "Display", group: "System", Component: DisplayPage },
];
