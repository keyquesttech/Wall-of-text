// Settings sub-pages, grouped as in Settings › index. DESIGN REVIEW: built from the shared
// components without the handoff's Settings mockups.
import type { FunctionComponent } from "preact";
import { signal } from "@preact/signals";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, get, send, upload, type FontInfo } from "../../lib/api";
import { inboxWaiting, printer, settings, wifi } from "../../lib/state";
import { IconBulb, IconCalendar, IconClock, IconCloud, IconDevice, IconEye, IconFont, IconHistory, IconLock, IconMail, IconPlus, IconPrinter, IconTrash, IconWifi } from "../../components/icons";
import { Banner, Seg, Sheet, timeAgo, toast, Toggle, ToggleRow, Topbar } from "../../components/ui";
import { AccessPage, useBack, WifiPage } from "../Settings";
import { RemotePage } from "./remote";

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
          options={["0", "1", "2", "4"].map((v) => ({ value: v, label: v === "0" ? "None" : `${v} lines` }))} />
      </div>
      <div class="glass grp" style="margin-top:12px">
        <ToggleRow label="Paper saver" sub="Tighter spacing and no blank space at the end." checked={p.paper_saver}
          onChange={(v) => patch({ printer: { paper_saver: v } })} />
        <ToggleRow label="Rotate prints 180°" sub="Turns every slip round so it reads the right way up as it hangs from the printer." checked={p.rotate_180 ?? true}
          onChange={(v) => patch({ printer: { rotate_180: v } })} />
      </div>
      <h2 class="section">Paper</h2>
      <div class="glass grp">
        <div class="lrow kv-row"><span class="grow">Left on the roll</span><span class="meta">About {printer.value?.paper_percent ?? 100}%</span></div>
        <button class="lrow" onClick={() => api.newRoll().then((x) => { printer.value = x; toast("Paper counter reset"); })}>I loaded a new roll</button>
        <button class="lrow" onClick={() => api.testPage().then(() => toast("Printing a test page"))}>Print a test page</button>
      </div>
      <p class="dim tiny" style="margin:8px 6px">The printer can't measure the roll, so this is an estimate from how much has been printed.</p>
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
function ButtonPage() {
  const back = useBack();
  const [s, patch] = useSettings();
  const [actions, setActions] = useState<{ id: string; label: string }[]>([]);
  useEffect(() => { get<{ id: string; label: string }[]>("/api/actions").then(setActions); }, []);
  if (!s) return null;
  const led = s.led;
  const events: [string, string][] = [["idle", "Idle"], ["printing", "Printing"], ["message_waiting", "New message waiting"], ["paper_out", "Paper out"], ["error", "Error"]];
  return (
    <>
      <Topbar title="Button & light" back={back} />
      <h2 class="section">Button</h2>
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
      <h2 class="section">Light</h2>
      <div class="glass card">
        <label class="field-label" for="bright" style="margin-top:0">Brightness</label>
        <input id="bright" type="range" min={0} max={100} step={5} value={led.brightness}
          onChange={(e) => patch({ led: { brightness: Number((e.target as HTMLInputElement).value) } })} />
      </div>
      <div class="glass grp" style="margin-top:12px">
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
          ["always", "Always print when back", "Even if it's hours late."]].map(([v, l, sub]) => (
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
      <h2 class="section">Time zone</h2>
      <div class="glass card">
        <select class="input" value={sc.timezone} aria-label="Time zone" onChange={(e) => patch({ schedules: { timezone: (e.target as HTMLSelectElement).value } })}>
          {(((Intl as any).supportedValuesOf?.("timeZone") as string[] | undefined) ?? ["Europe/London", "Europe/Dublin", "Europe/Paris", "America/New_York", "UTC"]).map((z) => <option value={z}>{z}</option>)}
        </select>
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
            {[50, 100, 200, 500].map((n) => <option value={n}>{n} prints</option>)}
          </select>
        </div>
        <div class="lrow"><span class="grow">For at most</span>
          <select class="input" style="width:auto" value={s.history.max_days} aria-label="Days kept" onChange={(e) => patch({ history: { max_days: Number((e.target as HTMLSelectElement).value) } })}>
            {[7, 14, 30, 90].map((n) => <option value={n}>{n} days</option>)}
          </select>
        </div>
      </div>
      <p class="dim tiny" style="margin:8px 6px">Whichever is fewer. Each print keeps a small picture of exactly what came out.</p>
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

// ----------------------------------------------------------- Guest & inbox --
export function GuestAndInbox() {
  const [s, patch] = useSettings();
  const [items, setItems] = useState<any[]>([]);
  const load = () => get<{ items: any[] }>("/api/inbox").then((r) => setItems(r.items));
  useEffect(() => { load(); }, [inboxWaiting.value]);
  if (!s) return null;
  const g = s.guest;
  return (
    <>
      <h2 class="section">Waiting for your OK</h2>
      <div class="glass grp">
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
      </div>
      <h2 class="section">Guest page</h2>
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

function DevicePage() {
  const back = useBack();
  const [d, setD] = useState<any>(null);
  const [confirm, setConfirm] = useState<null | "restart" | "shutdown">(null);
  const [restoring, setRestoring] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => { api.device().then(setD); const t = setInterval(() => api.device().then(setD), 10000); return () => clearInterval(t); }, []);
  const up = d ? `${Math.floor(d.uptime_s / 86400)}d ${Math.floor((d.uptime_s % 86400) / 3600)}h` : "";
  const hot = d?.temperature_c != null && d.temperature_c >= 75;
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
      <h2 class="section">Backup</h2>
      <div class="glass grp">
        <a class="lrow" href="/api/backup" download>Download a backup</a>
        <label class="lrow" for="restore" style="cursor:pointer">{restoring ? "Restoring…" : "Restore from a backup"}</label>
      </div>
      <input ref={file} id="restore" type="file" accept=".zip,application/zip" class="sr-only" onChange={restore} />
      <p class="dim tiny" style="margin:8px 6px">Backups hold settings, schedules, templates, lists and uploaded fonts. Passwords and connection secrets are never included.</p>
      <UsbBackupGroup />
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

export const SETTINGS_PAGES: SettingsPage[] = [
  { id: "printer", Icon: IconPrinter, title: "Printer", group: "Printing", Component: PrinterPage, meta: () => `About ${printer.value?.paper_percent ?? 100}% paper` },
  { id: "fonts", Icon: IconFont, title: "Fonts", group: "Printing", Component: FontsPage },
  { id: "button", Icon: IconBulb, title: "Button & light", group: "Printing", Component: ButtonPage },
  { id: "schedules", Icon: IconClock, title: "Schedules", group: "Printing", Component: SchedulePrefs, meta: () => (settings.value?.schedules?.holiday_mode ? "Holiday mode" : settings.value?.schedules?.quiet_hours?.enabled ? `Quiet ${settings.value.schedules.quiet_hours.start}–${settings.value.schedules.quiet_hours.end}` : "") },
  { id: "history", Icon: IconHistory, title: "History", group: "Printing", Component: HistoryPrefs },
  { id: "weather", Icon: IconCloud, title: "Weather", group: "Connections", Component: WeatherPage, meta: () => settings.value?.weather?.place || "Not set" },
  { id: "google", Icon: IconCalendar, title: "Google", group: "Connections", Component: GooglePage, meta: googleMeta },
  { id: "remote", Icon: IconMail, title: "Remote messages", group: "Connections", Component: RemotePage },
  { id: "access", Icon: IconLock, title: "Access", group: "Access", Component: AccessPage, meta: () => (inboxWaiting.value ? `${inboxWaiting.value} waiting` : "") },
  { id: "wifi", Icon: IconWifi, title: "Wi-Fi", group: "Device", Component: WifiPage, meta: () => wifi.value?.ssid ?? "" },
  { id: "device", Icon: IconDevice, title: "Device", group: "Device", Component: DevicePage },
  { id: "display", Icon: IconEye, title: "Display", group: "Device", Component: DisplayPage },
];
