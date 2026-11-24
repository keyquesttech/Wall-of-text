// Schedules (HANDOFF 7.2–7.4; Schedules, Wizard, Routine mockups). Pink = "later".
import { signal } from "@preact/signals";
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { get, send, type Doc } from "../lib/api";
import { settings } from "../lib/state";
import {
  IconAlarm, IconCalendar, IconCart, IconCloud, IconDown, IconHourglass, IconPin, IconPlus, IconQuote, IconRoutine,
  IconSun, IconTasks, IconTrash, IconUp, IconX, IconCreate,
} from "../components/icons";
import { StatusPill } from "../components/printer";
import { Banner, Seg, Sheet, timeAgo, toast, Toggle, Topbar } from "../components/ui";
import { googleState, loadGoogle } from "./settings/pages";

export interface Section { type: string; [k: string]: any }
export interface Condition { type: string; value?: number }
export interface Schedule {
  id: string; name: string; enabled: boolean; time: string | null; days: number[];
  sections: Section[]; conditions: Condition[]; next_run: number | null; last_run_at: number | null; last_result: string | null;
}
interface ListResp { items: Schedule[]; status: { clock_synced: boolean; holiday_mode: boolean; quiet_now: boolean; timezone: string }; sections: Record<string, string>; conditions: Record<string, string> }

const DAY1 = ["M", "T", "W", "T", "F", "S", "S"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAYN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const SECTION_ICON: Record<string, (p: any) => any> = {
  weather: IconCloud, agenda: IconCalendar, tasks: IconTasks, fortune: IconQuote, quote: IconQuote, countdown: IconHourglass,
  shopping: IconCart, message: IconCreate, date: IconSun, divider: IconRoutine,
};

export function whenText(s: { time: string | null; days: number[] }) {
  if (!s.time) return "From the button or a quick chip";
  const d = [...s.days].sort().join();
  const on = d === "0,1,2,3,4,5,6" ? "Every day" : d === "0,1,2,3,4" ? "Every weekday" : d === "5,6" ? "Every weekend day"
    : s.days.length === 1 ? `Every ${DAYN[s.days[0]]}` : s.days.length === 0 ? "Never (no days picked)" : s.days.map((x) => DAYS[x]).join(", ");
  return `${on} at ${s.time}`;
}

function whatText(s: Schedule, names: Record<string, string>) {
  return s.sections.map((x) => names[x.type] ?? x.type).join(" + ") || "Nothing yet";
}

function nextLabel(ts: number | null) {
  if (!ts) return "";
  const d = new Date(ts * 1000), now = new Date();
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return `next today ${hm}`;
  if (d.toDateString() === new Date(now.getTime() + 86400000).toDateString()) return `next tomorrow ${hm}`;
  return `next ${d.toLocaleDateString("en-GB", { weekday: "short" })} ${hm}`;
}

// --------------------------------------------------------------- wizard API --
interface WizardState { doc?: Doc; title?: string }
const wizard = signal<WizardState | null>(null);
const schedulesChanged = signal(0);
export function openWizard(doc?: Doc, title?: string) {
  wizard.value = { doc: doc && doc.blocks.length ? doc : undefined, title };
}

// ---------------------------------------------------------------------- list --
export function Schedules() {
  const { params } = useRoute();
  const { route } = useLocation();
  const [data, setData] = useState<ListResp | null>(null);
  const load = () => get<ListResp>("/api/schedules").then(setData);
  useEffect(() => { load(); }, [params.id, schedulesChanged.value]);

  if (params.id) return <Routine id={params.id} meta={data} onDone={() => { route("/schedules"); load(); }} />;
  const st = data?.status;
  const holiday = !!settings.value?.schedules?.holiday_mode;
  const timed = data?.items.filter((s) => s.time) ?? [];
  const routines = data?.items.filter((s) => !s.time) ?? [];
  const names = data?.sections ?? {};
  return (
    <>
      <Topbar title="Schedules" right={<button class="btn-pink" style="min-height:44px;padding:0 16px;font-size:15px" onClick={() => openWizard()}><IconPlus class="i" style="stroke-width:2.4" />New</button>}>
        <StatusPill />
      </Topbar>
      {st && !st.clock_synced && <Banner>Waiting for the clock. After a power cut the printer sets its clock from the internet; schedules start once it has.</Banner>}
      {st?.quiet_now && !holiday && <Banner kind="warn">Quiet hours now. Scheduled prints wait until they end.</Banner>}
      <div class="glass" style="border-radius:20px;display:flex;align-items:center;gap:12px;padding:12px 14px">
        <span class="ico p"><IconSun class="i" /></span>
        <div class="grow" style="display:flex;flex-direction:column"><span class="h3" style="font-size:16px">Holiday mode</span><span class="cap">Pause every schedule until you're back</span></div>
        <Toggle pink label="Holiday mode" checked={holiday} onChange={(v) => send("PATCH", "/api/settings", { schedules: { holiday_mode: v } }).then((s) => (settings.value = s))} />
      </div>
      {data && data.items.length === 0 && <Empty onStarter={async () => {
        const s = await send<Schedule>("POST", "/api/schedules", { name: "Morning briefing", time: "07:30", days: [0, 1, 2, 3, 4], sections: [{ type: "date" }, { type: "weather" }, { type: "agenda" }, { type: "tasks" }, { type: "fortune" }], conditions: [] });
        route(`/schedules/${s.id}`);
      }} />}
      {timed.length > 0 && <Timeline items={timed.filter((s) => s.enabled && !holiday)} />}
      {timed.map((s) => <Card s={s} names={names} onToggle={load} onOpen={() => route(`/schedules/${s.id}`)} />)}
      {routines.length > 0 && (
        <>
          <span class="sect">Routines · run from the button or a quick chip</span>
          {routines.map((s) => <Card s={s} names={names} onToggle={load} onOpen={() => route(`/schedules/${s.id}`)} />)}
        </>
      )}
    </>
  );
}

function Empty(props: { onStarter: () => void }) {
  return (
    <div class="empty">
      <svg class="illo" viewBox="0 0 160 140" aria-hidden="true">
        <defs><filter id="gl"><feGaussianBlur stdDeviation="4" /></filter></defs>
        <rect x="44" y="20" width="62" height="96" rx="4" fill="#F7F5F0" />
        <path d="M44 112l6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6V20H44z" fill="#F7F5F0" />
        <path d="M54 38h42M54 52h30M54 66h36" stroke="#121315" stroke-width="4" stroke-linecap="round" />
        <circle cx="110" cy="88" r="26" fill="#FF2E9A" filter="url(#gl)" opacity=".7" />
        <circle cx="110" cy="88" r="24" fill="#1C1D21" stroke="#FF2E9A" stroke-width="3" />
        <path d="M110 74v14l9 6" stroke="#FF63B4" stroke-width="3.5" stroke-linecap="round" fill="none" />
      </svg>
      <h2 class="h2">Nothing scheduled yet</h2>
      <p style="font-size:16px;line-height:22px">Set a print to happen on its own, like an alarm. A morning briefing is a nice first one.</p>
      <button class="btn-pink" onClick={() => openWizard()}><IconPlus class="i" style="stroke-width:2.4" />New schedule</button>
      <button class="glass btn" style="color:var(--hi)" onClick={props.onStarter}>Start from “Morning briefing”</button>
    </div>
  );
}

/** Up next · today: a 06:00–24:00 track with past (hollow, ✓), now, and upcoming (pink) prints. */
function Timeline({ items }: { items: Schedule[] }) {
  const now = new Date();
  const dow = (now.getDay() + 6) % 7;
  const minsNow = now.getHours() * 60 + now.getMinutes();
  const pts = items.filter((s) => s.days.includes(dow)).map((s) => {
    const [h, m] = s.time!.split(":").map(Number);
    return { s, mins: h * 60 + m };
  }).filter((p) => p.mins >= 360).sort((a, b) => a.mins - b.mins);
  const pos = (mins: number) => `${Math.min(100, Math.max(0, ((mins - 360) / (1440 - 360)) * 100))}%`;
  const next = pts.find((p) => p.mins > minsNow);
  const until = next ? next.mins - minsNow : 0;
  const untilText = next ? `${next.s.name} in ${until >= 60 ? `${Math.floor(until / 60)} h ` : ""}${until % 60} min` : "Nothing more today";
  return (
    <section class="glass tp" style="padding:14px 16px 16px;border-radius:22px" aria-label="Up next today">
      <div class="row" style="justify-content:space-between;margin-bottom:14px">
        <span class="lbl">Up next · today</span>
        <span style="font-size:13px;font-weight:700;color:var(--pink-text)">{untilText}</span>
      </div>
      <div class="timeline">
        <div class="track" />
        <div class="past" style={{ width: pos(minsNow) }} />
        {minsNow >= 360 && <div class="now" style={{ left: pos(minsNow) }} />}
        {pts.map((p) => {
          const done = p.mins <= minsNow;
          const isNext = next && p.s.id === next.s.id;
          return (
            <>
              <div class={`pt ${done ? "done" : isNext ? "next" : "up"}`} style={{ left: pos(p.mins) }} title={`${p.s.time} ${p.s.name}`} />
              <span class="tl" style={{ left: pos(p.mins), color: done ? "var(--muted)" : isNext ? "var(--pink-text)" : "var(--silver)", fontWeight: isNext ? 700 : 400 }}>{p.s.time}{done ? " ✓" : ""}</span>
            </>
          );
        })}
        {minsNow >= 360 && <span class="tl" style={{ left: pos(minsNow), top: "-14px", color: "var(--hi)", fontWeight: 700 }}>Now</span>}
      </div>
    </section>
  );
}

function Card({ s, names, onToggle, onOpen }: { s: Schedule; names: Record<string, string>; onToggle: () => void; onOpen: () => void }) {
  const Ico = SECTION_ICON[s.sections[0]?.type ?? "routine"] ?? IconRoutine;
  let last = "";
  try {
    const r = s.last_result ? JSON.parse(s.last_result) : null;
    if (r && s.last_run_at && r.state !== "printed") last = ` · ${r.state === "held" ? "held" : r.state === "skipped" ? "skipped" : "missed"} ${timeAgo(s.last_run_at)}`;
  } catch { /* ignore */ }
  const off = !s.enabled && !!s.time;
  return (
    <div class={`glass scard ${off ? "off" : ""}`}>
      <button class="row grow" style="text-align:left;gap:12px" onClick={onOpen} aria-label={`${s.name}, ${whenText(s)}. Edit`}>
        <span class={`ico big ${off ? "" : "p"}`}><Ico class="i" /></span>
        <span class="grow" style="display:flex;flex-direction:column;gap:2px">
          <span class="h3" style="font-size:16px">{s.name}</span>
          <span class="when">{whenText(s)}</span>
          <span class="cap" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{whatText(s, names)}{s.enabled && s.next_run ? ` · ${nextLabel(s.next_run)}` : ""}{last}</span>
        </span>
      </button>
      {s.time && <Toggle pink label={`${s.name} on or off`} checked={s.enabled} onChange={(v) => send("PATCH", `/api/schedules/${s.id}`, { enabled: v }).then(onToggle)} />}
    </div>
  );
}

// ------------------------------------------------------------------- pickers --
/** Wheel time picker in 5-minute steps (HANDOFF 6). Arrow keys and the mouse wheel work too. */
export function TimeWheel(props: { value: string; onChange: (v: string) => void }) {
  const [h, m] = props.value.split(":").map(Number);
  const set = (hh: number, mm: number) => props.onChange(`${String((hh + 24) % 24).padStart(2, "0")}:${String((mm + 60) % 60).padStart(2, "0")}`);
  const col = (val: number, max: number, step: number, apply: (v: number) => void, label: string) => {
    const vals = [-2, -1, 0, 1, 2].map((k) => (val + k * step + max * 10) % max);
    return (
      <div class="wcol" role="spinbutton" tabIndex={0} aria-label={label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={max - step}
        onKeyDown={(e) => { if (e.key === "ArrowUp") { apply(val - step); e.preventDefault(); } if (e.key === "ArrowDown") { apply(val + step); e.preventDefault(); } }}
        onWheel={(e) => { e.preventDefault(); apply(val + (e.deltaY > 0 ? step : -step)); }}>
        {vals.map((v, k) => (
          <button type="button" tabIndex={-1} aria-hidden="true" class="" onClick={() => apply(v)}>
            <span class={k === 2 ? "cur" : k === 0 || k === 4 ? "far" : ""}>{String(v).padStart(2, "0")}</span>
          </button>
        ))}
      </div>
    );
  };
  const mm5 = Math.round(m / 5) * 5 % 60;
  return (
    <div class="wheel" aria-label={`Time ${props.value}`}>
      <div class="glass band" />
      {col(h, 24, 1, (v) => set(v, mm5), "Hour")}
      <span class="colon">:</span>
      {col(mm5, 60, 5, (v) => set(h, v), "Minutes")}
    </div>
  );
}

export function DayChips(props: { days: number[]; onChange: (d: number[]) => void }) {
  return (
    <div class="daysrow" role="group" aria-label="Days">
      {DAY1.map((d, i) => (
        <button type="button" class={`day ${props.days.includes(i) ? "on" : ""}`} aria-pressed={props.days.includes(i)} aria-label={DAYN[i]}
          onClick={() => props.onChange(props.days.includes(i) ? props.days.filter((x) => x !== i) : [...props.days, i].sort())}>{d}</button>
      ))}
    </div>
  );
}

function firstRunText(time: string, days: number[]) {
  if (!days.length) return "Pick at least one day.";
  const now = new Date();
  const [h, m] = time.split(":").map(Number);
  for (let k = 0; k < 8; k++) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + k, h, m);
    if (d > now && days.includes((d.getDay() + 6) % 7)) return k === 0 ? "First one today." : k === 1 ? "First one tomorrow." : `First one on ${DAYN[(d.getDay() + 6) % 7]}.`;
  }
  return "";
}

// -------------------------------------------------------------------- wizard --
const SOURCES: { id: string; name: string; sub: string; Icon: (p: any) => any; sections: Section[]; defName: string }[] = [
  { id: "weather", name: "Weather", sub: "Today's forecast", Icon: IconCloud, sections: [{ type: "weather" }], defName: "Weather" },
  { id: "agenda", name: "Calendar agenda", sub: "What's on today", Icon: IconCalendar, sections: [{ type: "agenda" }], defName: "Today's agenda" },
  { id: "tasks", name: "Tasks", sub: "Google Tasks to do", Icon: IconTasks, sections: [{ type: "tasks" }], defName: "To do" },
  { id: "countdown", name: "Countdown", sub: "Days until something", Icon: IconHourglass, sections: [{ type: "countdown", date: "", label: "" }], defName: "Countdown" },
  { id: "fortune", name: "Quote or fortune", sub: "A little line", Icon: IconQuote, sections: [{ type: "fortune" }], defName: "Daily fortune" },
  { id: "shopping", name: "Shopping list", sub: "If it has items", Icon: IconCart, sections: [{ type: "shopping", skip_empty: true }], defName: "Shopping list" },
  { id: "routine", name: "Routine", sub: "Date, weather, agenda, tasks, quote", Icon: IconRoutine, sections: [{ type: "date" }, { type: "weather" }, { type: "agenda" }, { type: "tasks" }, { type: "fortune" }], defName: "Morning briefing" },
];
const STEP_NAMES = ["What", "When", "Options", "Preview"];
const STEP_TITLES = ["What should it print?", "When should it print?", "Any options?", "Check and save"];
type Freq = "daily" | "weekdays" | "weekends" | "weekly" | "custom";

export function WizardHost() {
  const w = wizard.value;
  if (!w) return null;
  return <Wizard key={JSON.stringify(w).length} init={w} onClose={() => (wizard.value = null)} />;
}

function Wizard({ init, onClose }: { init: WizardState; onClose: () => void }) {
  const { route } = useLocation();
  const [step, setStep] = useState(1);
  const [src, setSrc] = useState(init.doc ? "message" : "weather");
  const [freq, setFreq] = useState<Freq>("daily");
  const [time, setTime] = useState("07:45");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [conds, setConds] = useState<Condition[]>([]);
  const [cd, setCd] = useState({ label: "", date: "" });
  const [name, setName] = useState("");
  const [pv, setPv] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const source = SOURCES.find((s) => s.id === src);
  const sections: Section[] = useMemo(() => {
    if (src === "message") return [{ type: "message", document: init.doc }];
    const secs = source?.sections.map((x) => ({ ...x })) ?? [];
    return secs.map((x) => (x.type === "countdown" ? { ...x, ...cd } : x));
  }, [src, cd]);
  const setF = (f: Freq) => {
    setFreq(f);
    if (f === "daily") setDays([0, 1, 2, 3, 4, 5, 6]);
    if (f === "weekdays") setDays([0, 1, 2, 3, 4]);
    if (f === "weekends") setDays([5, 6]);
    if (f === "weekly") setDays([(new Date().getDay() + 6) % 7]);
  };
  useEffect(() => { if (step === 4 && !name) setName(src === "message" ? init.title || "My message" : source?.defName ?? "Schedule"); }, [step]);
  useEffect(() => {
    if (step !== 4) return;
    setPv(null);
    fetch("/api/schedules/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sections }) })
      .then((r) => (r.ok ? r.blob() : null)).then((b) => b && setPv(URL.createObjectURL(b))).catch(() => {});
  }, [step]);
  const canNext = step === 1 ? !!src : step === 2 ? days.length > 0 : step === 3 ? (src !== "countdown" || !!cd.date) : !!name.trim();
  const save = async () => {
    setBusy(true);
    try {
      await send<Schedule>("POST", "/api/schedules", { name: name.trim(), time, days, sections, conditions: conds, enabled: true });
      toast(`Scheduled for ${time}`);
      schedulesChanged.value++;
      onClose();
      route("/schedules");
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  const condRow = (type: string, title: string, sub: string, value?: number) => {
    const on = conds.some((c) => c.type === type);
    return (
      <div class="lrow">
        <div class="grow" style="display:flex;flex-direction:column"><span>{title}</span><span class="cap">{sub}</span></div>
        <Toggle pink label={title} checked={on} onChange={(v) => setConds(v ? [...conds, { type, ...(value !== undefined ? { value } : {}) }] : conds.filter((c) => c.type !== type))} />
      </div>
    );
  };
  const quiet = settings.value?.schedules?.quiet_hours;
  return (
    <div class="scrimf" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <section class="glass sheetf tp" role="dialog" aria-modal="true" aria-label="New schedule" style="display:flex;flex-direction:column;gap:14px;max-height:94vh">
        <div class="grab" />
        <div class="row" style="justify-content:space-between;align-items:flex-start">
          <div style="display:flex;flex-direction:column;gap:2px">
            <span class="lbl" style="color:var(--pink-text)">Step {step} of 4 · {STEP_NAMES[step - 1]}</span>
            <h2 class="h2">{STEP_TITLES[step - 1]}</h2>
          </div>
          <button class="ib" aria-label="Close" style="background:rgba(201,205,212,.12)" onClick={onClose}><IconX class="i" /></button>
        </div>
        <div class="wizbar">{[1, 2, 3, 4].map((k) => <div class="bar pk"><i style={{ width: k <= step ? "100%" : "0%" }} /></div>)}</div>

        {step === 1 && (
          <div class="wtiles">
            {init.doc && (
              <Tile on={src === "message"} onClick={() => setSrc("message")} Icon={IconCreate} name="My message" sub={`${init.title ? `“${init.title}” ` : ""}attached from Create`} />
            )}
            {SOURCES.map((s) => <Tile on={src === s.id} onClick={() => setSrc(s.id)} Icon={s.Icon} name={s.name} sub={s.sub} />)}
          </div>
        )}
        {step === 2 && (
          <>
            <div class="chips wrapc">
              {([["daily", "Daily"], ["weekdays", "Weekdays"], ["weekends", "Weekends"], ["weekly", "Weekly"], ["custom", "Pick days"]] as const).map(([f, l]) => (
                <button class={`glass chip pk`} aria-pressed={freq === f} onClick={() => setF(f)}>{l}</button>
              ))}
            </div>
            <TimeWheel value={time} onChange={setTime} />
            <DayChips days={days} onChange={(d) => { setDays(d); setFreq("custom"); }} />
            <div class="glass summary"><IconAlarm class="i" /><span>Prints <b>{whenText({ time, days }).replace(/^Every/, "every")}</b>. {firstRunText(time, days)}</span></div>
          </>
        )}
        {step === 3 && (
          <>
            {(src === "weather" || src === "routine") && (
              <>
                <div class="glass grp">
                  <a class="lrow" href="/settings/weather" onClick={onClose}><span class="ico p"><IconPin class="i" /></span>Location<span class="v">{settings.value?.weather?.place || "Not set"}</span><span class="chevr">›</span></a>
                  <div class="lrow">Units
                    <div style="margin-left:auto"><Seg small width="120px" label="Units" value={settings.value?.weather?.units ?? "C"}
                      onChange={(v) => send("PATCH", "/api/settings", { weather: { units: v } }).then((s) => (settings.value = s))}
                      options={[{ value: "C", label: "°C" }, { value: "F", label: "°F" }]} /></div>
                  </div>
                </div>
                <span class="sect">Only print if</span>
                <div class="glass grp">
                  {condRow("rain_above", "Rain is likely", "Chance of rain 50% or more", 50)}
                  {condRow("temp_below", "It drops below", "3 °C when it's time to print", 3)}
                </div>
              </>
            )}
            {(src === "agenda" || src === "tasks") && <GoogleHint />}
            {src === "agenda" && <div class="glass grp">{condRow("has_events", "Only if there's something on", "Skip days with an empty calendar")}</div>}
            {src === "tasks" && <div class="glass grp">{condRow("has_tasks", "Only if any are due", "Skip when there's nothing to do")}</div>}
            {src === "countdown" && (
              <div class="glass card stack">
                <label class="field-label" for="cdl" style="margin-top:0">What are you counting down to?</label>
                <input id="cdl" class="input" placeholder="Holiday" value={cd.label} maxLength={40} onInput={(e) => setCd({ ...cd, label: (e.target as HTMLInputElement).value })} />
                <label class="field-label" for="cdd">Date</label>
                <input id="cdd" class="input" type="date" value={cd.date} onInput={(e) => setCd({ ...cd, date: (e.target as HTMLInputElement).value })} />
              </div>
            )}
            {["message", "fortune", "shopping"].includes(src) && <p class="cap">Nothing else to set for this one.</p>}
            <div class="glass grp"><div class="lrow"><div class="grow" style="display:flex;flex-direction:column"><span>Quiet hours</span><span class="cap">{quiet?.enabled ? `${quiet.start} to ${quiet.end}: prints wait until they end. Change in Settings.` : "Off. Turn on in Settings › Schedules."}</span></div></div></div>
          </>
        )}
        {step === 4 && (
          <>
            <div class="glass" style="border-radius:16px;padding:4px 4px 4px 14px;display:flex;align-items:center;gap:10px">
              <label for="wname" class="cap" style="color:var(--silver)">Name</label>
              <input id="wname" value={name} maxLength={60} onInput={(e) => setName((e.target as HTMLInputElement).value)} style="flex:1;height:44px;border:0;background:transparent;outline:none;font-size:16px;font-weight:600;color:var(--hi)" />
            </div>
            <div style="display:flex;justify-content:center">
              <div class="rwrap" style="width:250px"><div class="receipt bits img">{pv ? <img src={pv} alt="What it will print" /> : <div class="shim" style="height:180px;margin:0 10px" />}</div></div>
            </div>
            <p class="cap center">{src === "message" ? "It prints exactly this each time." : "Preview uses today's data. Each print uses the data of its day."}</p>
          </>
        )}
        <div class="actrow">
          <button class="btn" style="width:110px;min-height:56px" onClick={() => (step === 1 ? onClose() : setStep(step - 1))}>{step === 1 ? "Cancel" : "Back"}</button>
          <button class="btn-pink" style="flex:1;min-height:56px" disabled={!canNext || busy} onClick={() => (step < 4 ? setStep(step + 1) : save())}>{step < 4 ? "Next" : "Save schedule"}</button>
        </div>
      </section>
    </div>
  );
}

function Tile(props: { on: boolean; onClick: () => void; Icon: (p: any) => any; name: string; sub: string }) {
  return (
    <button class={`glass wtile ${props.on ? "sel" : ""}`} aria-pressed={props.on} onClick={props.onClick}>
      <span class={`ico ${props.on ? "p" : ""}`}><props.Icon class="i" /></span>
      <span style="display:flex;flex-direction:column;gap:1px"><span class="n">{props.name}</span><span class="s">{props.sub}</span></span>
    </button>
  );
}

// ------------------------------------------------------- routine builder / edit --
function Routine(props: { id: string; meta: ListResp | null; onDone: () => void }) {
  const [s, setS] = useState<Schedule | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [pv, setPv] = useState<string | null>(null);
  useEffect(() => { get<Schedule>(`/api/schedules/${props.id}`).then(setS).catch(props.onDone); }, [props.id]);
  const set = (p: Partial<Schedule>) => setS((x) => (x ? { ...x, ...p } : x));
  const key = JSON.stringify(s?.sections ?? []);
  useEffect(() => {
    if (!s || !s.sections.length) { setPv(null); return; }
    const t = window.setTimeout(() => {
      fetch("/api/schedules/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sections: s.sections }) })
        .then((r) => (r.ok ? r.blob() : null)).then((b) => b && setPv(URL.createObjectURL(b))).catch(() => {});
    }, 500);
    return () => window.clearTimeout(t);
  }, [key]);
  if (!s) return <div class="stack"><div class="shim" style="height:60px" /><div class="shim" style="height:220px" /></div>;
  const secNames = props.meta?.sections ?? {};
  const condNames = props.meta?.conditions ?? {};
  const save = async () => {
    if (s.sections.some((x) => x.type === "countdown" && !x.date)) return toast("Pick a date for the countdown.");
    await send("PATCH", `/api/schedules/${s.id}`, { name: s.name, time: s.time, days: s.days, sections: s.sections, conditions: s.conditions, enabled: s.enabled });
    toast(s.time ? `Scheduled for ${s.time}` : "Saved");
    props.onDone();
  };
  const move = (i: number, d: number) => {
    const xs = s.sections.slice();
    const j = i + d;
    if (j < 0 || j >= xs.length) return;
    [xs[i], xs[j]] = [xs[j], xs[i]];
    set({ sections: xs });
  };
  const updSec = (i: number, p: Partial<Section>) => set({ sections: s.sections.map((x, k) => (k === i ? { ...x, ...p } : x)) });
  const condFor = (type: string) => {
    const map: Record<string, string> = { weather: "rain_above", agenda: "has_events", tasks: "has_tasks" };
    const c = s.conditions.find((x) => x.type === map[type]);
    return c ? (c.type === "rain_above" ? "If rain likely" : c.type === "has_events" ? "Only if any events" : "Only if any due") : null;
  };
  return (
    <>
      <Topbar title={s.name || "Routine"} back={props.onDone} backLabel="Schedules"><StatusPill /></Topbar>
      <div class="glass" style="border-radius:16px;padding:4px 4px 4px 14px;display:flex;align-items:center;gap:10px">
        <label for="sname" class="cap" style="color:var(--silver)">Name</label>
        <input id="sname" value={s.name} maxLength={60} onInput={(e) => set({ name: (e.target as HTMLInputElement).value })} style="flex:1;height:44px;border:0;background:transparent;outline:none;font-size:16px;font-weight:600;color:var(--hi)" />
      </div>

      <span class="sect">Blocks</span>
      {s.sections.map((sec, i) => {
        const Ico = SECTION_ICON[sec.type] ?? IconRoutine;
        const c = condFor(sec.type);
        return (
          <div class="glass block-row" style="flex-wrap:wrap">
            <span class="num">{i + 1}</span>
            <span class="ico"><Ico class="i" /></span>
            <div class="grow" style="display:flex;flex-direction:column;gap:4px">
              <span style="color:var(--hi);font-weight:600">{secNames[sec.type] ?? sec.type}</span>
              {c && <span class="cchip">{c}</span>}
            </div>
            <button class="ib" aria-label={`Move ${secNames[sec.type]} up`} disabled={i === 0} onClick={() => move(i, -1)}><IconUp class="i" /></button>
            <button class="ib" aria-label={`Move ${secNames[sec.type]} down`} disabled={i === s.sections.length - 1} onClick={() => move(i, 1)}><IconDown class="i" /></button>
            <button class="ib" aria-label={`Remove ${secNames[sec.type]}`} onClick={() => set({ sections: s.sections.filter((_, k) => k !== i) })}><IconTrash class="i" /></button>
            {sec.type === "quote" && <textarea class="input" style="min-height:70px;width:100%" placeholder="Your line" value={sec.text ?? ""} maxLength={400} aria-label="Your line" onInput={(e) => updSec(i, { text: (e.target as HTMLTextAreaElement).value })} />}
            {sec.type === "countdown" && (
              <div class="row" style="width:100%">
                <input class="input grow" placeholder="What (e.g. Holiday)" aria-label="Counting down to" value={sec.label ?? ""} maxLength={40} onInput={(e) => updSec(i, { label: (e.target as HTMLInputElement).value })} />
                <input class="input" type="date" style="width:170px" aria-label="Date" value={sec.date ?? ""} onInput={(e) => updSec(i, { date: (e.target as HTMLInputElement).value })} />
              </div>
            )}
          </div>
        );
      })}
      <button class="add-row" onClick={() => setAdding(true)}><IconPlus class="i" width={18} />Add a block</button>

      <span class="sect">When</span>
      <div class="glass card stack">
        <div class="row" style="justify-content:space-between"><span>Print at a set time</span>
          <Toggle pink label="Print at a set time" checked={!!s.time} onChange={(v) => set({ time: v ? "07:30" : null })} /></div>
        {s.time && (<><TimeWheel value={s.time} onChange={(time) => set({ time })} /><DayChips days={s.days} onChange={(days) => set({ days })} /></>)}
        <p class="cap">{s.time ? `${whenText(s)}. ${firstRunText(s.time, s.days)}` : "Without a time, run it from the arcade button or a quick chip on Create."}</p>
      </div>

      {s.time && (
        <>
          <span class="sect">Only print if</span>
          <div class="glass grp">
            {Object.entries(condNames).map(([type, label]) => {
              const on = s.conditions.some((c) => c.type === type);
              const val = s.conditions.find((c) => c.type === type)?.value;
              const def = type === "rain_above" ? 50 : type === "temp_below" ? 3 : type === "temp_above" ? 22 : undefined;
              return (
                <div class="lrow">
                  <span class="grow">{label}{on && val !== undefined ? "" : ""}</span>
                  {on && def !== undefined && (
                    <input class="input" type="number" style="width:84px;min-height:40px" aria-label={`${label} value`} value={val}
                      onInput={(e) => set({ conditions: s.conditions.map((c) => (c.type === type ? { ...c, value: Number((e.target as HTMLInputElement).value) } : c)) })} />
                  )}
                  <Toggle pink label={label} checked={on} onChange={(v) => set({ conditions: v ? [...s.conditions, { type, ...(def !== undefined ? { value: def } : {}) }] : s.conditions.filter((c) => c.type !== type) })} />
                </div>
              );
            })}
          </div>
          <p class="cap">If the data isn't available when it's time, it prints anyway with a short note.</p>
        </>
      )}

      <span class="sect">Preview</span>
      <div style="display:flex;justify-content:center">
        <div class="rwrap" style="max-width:300px">{s.sections.length ? <div class="receipt bits img">{pv ? <img src={pv} alt="What it will print today" /> : <div class="shim" style="height:180px;margin:0 10px" />}</div> : <p class="cap">Add a block to see it.</p>}</div>
      </div>
      <div class="actrow">
        <button class="btn-green" style="flex:1" disabled={!s.sections.length} onClick={() => send<{ message: string }>("POST", `/api/schedules/${s.id}/run`).then((r) => toast(r.message))}>Print now</button>
        <button class="btn-pink" style="flex:1" onClick={save}>{s.time ? "Save schedule" : "Save routine"}</button>
      </div>
      <button class="btn btn-danger" onClick={() => setConfirmDel(true)}><IconTrash class="i" />Delete</button>

      <Sheet open={adding} onClose={() => setAdding(false)} title="Add a block" tint="tp">
        <div class="wtiles">
          {Object.entries(secNames).filter(([k]) => k !== "message").map(([k, v]) => {
            const Ico = SECTION_ICON[k] ?? IconRoutine;
            return <Tile on={false} Icon={Ico} name={v} sub="" onClick={() => { set({ sections: [...s.sections, k === "countdown" ? { type: k, date: "", label: "" } : k === "quote" ? { type: k, text: "" } : { type: k }] }); setAdding(false); }} />;
          })}
        </div>
      </Sheet>
      <Sheet open={confirmDel} onClose={() => setConfirmDel(false)} title={`Delete “${s.name}”?`}>
        <div class="stack">
          <button class="btn-pink" onClick={() => send("DELETE", `/api/schedules/${s.id}`).then(() => { toast("Deleted"); props.onDone(); })}>Delete</button>
          <button class="btn" onClick={() => setConfirmDel(false)}>Cancel</button>
        </div>
      </Sheet>
    </>
  );
}

export type { ComponentChildren };

/** In the wizard: Calendar and Tasks need the Google sign-in first. */
function GoogleHint() {
  useEffect(() => { loadGoogle(); }, []);
  const g = googleState.value;
  if (!g || g.connected) return null;
  return (
    <Banner action={<a class="btn small" href="/settings/google">Connect</a>}>
      Connect your Google account first, or this prints "Google isn't connected".
    </Banner>
  );
}
