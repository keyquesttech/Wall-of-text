// Schedules (HANDOFF 7.2–7.4; Schedules, Wizard, Routine mockups). Pink = "later".
import { signal } from "@preact/signals";
import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { get, send, type Doc } from "../lib/api";
import { settings } from "../lib/state";
import {
  IconAlarm, IconCalendar, IconCart, IconCloud, IconDown, IconHourglass, IconPlus, IconQuote, IconRoutine,
  IconSun, IconTasks, IconTrash, IconUp, IconCreate,
} from "../components/icons";
import { StatusPill } from "../components/printer";
import { Banner, Seg, Sheet, timeAgo, toast, Toggle, Topbar } from "../components/ui";
import { googleState, loadGoogle } from "./settings/pages";

export interface Section { type: string; [k: string]: any }
export interface Condition { type: string; value?: number }
export interface Schedule {
  id: string; name: string; enabled: boolean; time: string | null; days: number[]; once?: string | null;
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

export function whenText(s: { time: string | null; days: number[]; once?: string | null }) {
  if (!s.time) return "From the button or a quick chip";
  if (s.once) { const t = onceText(s.once, s.time); return `Once, ${t}`; }
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
/** Create's Schedule button: schedule this message (a small sheet, not the full editor). */
export function openWizard(doc?: Doc, title?: string) {
  if (!doc || !doc.blocks.length) { toast("Make something first, then schedule it."); return; }
  wizard.value = { doc, title };
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
      <Topbar title="Schedules" right={<button class="btn-pink" style="min-height:44px;padding:0 16px;font-size:15px" onClick={() => route("/schedules/new")}><IconPlus class="i" style="stroke-width:2.4" />New</button>}>
        <StatusPill />
      </Topbar>
      {st && !st.clock_synced && <Banner>Waiting for the clock. After a power cut the printer sets its clock from the internet; schedules start once it has.</Banner>}
      {st?.quiet_now && !holiday && <Banner kind="warn">Quiet hours now. Scheduled prints wait until they end.</Banner>}
      <div class="glass" style="border-radius:20px;display:flex;align-items:center;gap:12px;padding:12px 14px">
        <span class="ico p"><IconSun class="i" /></span>
        <div class="grow" style="display:flex;flex-direction:column"><span class="h3" style="font-size:16px">Holiday mode</span><span class="cap">Pause every schedule until you're back</span></div>
        <Toggle pink label="Holiday mode" checked={holiday} onChange={(v) => send("PATCH", "/api/settings", { schedules: { holiday_mode: v } }).then((s) => (settings.value = s))} />
      </div>
      {data && data.items.length === 0 && <Empty onNew={() => route("/schedules/new")} onStarter={async () => {
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

function Empty(props: { onStarter: () => void; onNew: () => void }) {
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
      <button class="btn-pink" onClick={props.onNew}><IconPlus class="i" style="stroke-width:2.4" />New schedule</button>
      <button class="glass btn" style="color:var(--hi)" onClick={props.onStarter}>Start from “Morning briefing”</button>
    </div>
  );
}

/** Up next · today: a 06:00–24:00 track with past (hollow, ✓), now, and upcoming (pink) prints. */
function Timeline({ items }: { items: Schedule[] }) {
  const now = new Date();
  const dow = (now.getDay() + 6) % 7;
  const minsNow = now.getHours() * 60 + now.getMinutes();
  const todayIso = iso(now);
  const pts = items.filter((s) => (s.once ? s.once === todayIso : s.days.includes(dow))).map((s) => {
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
/** Ready-made block sets for a new schedule (the editor's "Start from" chips). */
const STARTERS: { id: string; name: string; Icon: (p: any) => any; sections: Section[]; defName: string }[] = [
  { id: "briefing", name: "Morning briefing", Icon: IconRoutine, sections: [{ type: "date" }, { type: "weather" }, { type: "agenda" }, { type: "tasks" }, { type: "fortune" }], defName: "Morning briefing" },
  { id: "weather", name: "Weather", Icon: IconCloud, sections: [{ type: "weather" }], defName: "Weather" },
  { id: "agenda", name: "Calendar", Icon: IconCalendar, sections: [{ type: "agenda" }], defName: "Today's agenda" },
  { id: "tasks", name: "Tasks", Icon: IconTasks, sections: [{ type: "tasks" }], defName: "To do" },
  { id: "fortune", name: "Fortune", Icon: IconQuote, sections: [{ type: "fortune" }], defName: "Daily fortune" },
  { id: "shopping", name: "Shopping list", Icon: IconCart, sections: [{ type: "shopping", skip_empty: true }], defName: "Shopping list" },
  { id: "countdown", name: "Countdown", Icon: IconHourglass, sections: [{ type: "countdown", date: "", label: "" }], defName: "Countdown" },
];
type Freq = "daily" | "weekdays" | "weekends" | "weekly" | "custom";
const FREQS: [Freq, string][] = [["daily", "Daily"], ["weekdays", "Weekdays"], ["weekends", "Weekends"], ["weekly", "Weekly"], ["custom", "Pick days"]];
const daysFor = (f: Freq, cur: number[]) => (f === "daily" ? [0, 1, 2, 3, 4, 5, 6] : f === "weekdays" ? [0, 1, 2, 3, 4] : f === "weekends" ? [5, 6] : f === "weekly" ? [(new Date().getDay() + 6) % 7] : cur);
const freqOf = (days: number[]): Freq => { const d = [...days].sort().join(); return d === "0,1,2,3,4,5,6" ? "daily" : d === "0,1,2,3,4" ? "weekdays" : d === "5,6" ? "weekends" : "custom"; };
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const atTime = (date: string, time: string) => new Date(`${date}T${time}:00`);
function onceText(date: string, time: string) {
  const d = atTime(date, time), now = new Date();
  const day = iso(d) === iso(now) ? "today" : iso(d) === iso(new Date(now.getTime() + 86400000)) ? "tomorrow"
    : d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  return `${day} at ${time}`;
}
/** A sensible first time for a one-off: 30 minutes from now, on a 5-minute step. */
function soon() {
  const d = new Date(Date.now() + 30 * 60000);
  d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
  return { date: iso(d), time: `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` };
}

/** When: once on a date, or repeating on week days (shared by the message sheet and the editor). */
function WhenPicker(props: { kind: "once" | "repeat"; date: string; time: string; days: number[]; onChange: (p: { date?: string; time?: string; days?: number[] }) => void }) {
  const [freq, setFreq] = useState<Freq>(freqOf(props.days));
  const today = iso(new Date()), tomorrow = iso(new Date(Date.now() + 86400000));
  return (
    <div class="stack">
      {props.kind === "once" ? (
        <div class="chips wrapc" role="group" aria-label="Day">
          <button type="button" class="glass chip pk" aria-pressed={props.date === today} onClick={() => props.onChange({ date: today })}>Today</button>
          <button type="button" class="glass chip pk" aria-pressed={props.date === tomorrow} onClick={() => props.onChange({ date: tomorrow })}>Tomorrow</button>
          <label class="sr-only" for="oncedate">Date</label>
          <input id="oncedate" type="date" class="input" style="width:auto;flex:1;min-width:150px" min={today} value={props.date} onInput={(e) => props.onChange({ date: (e.target as HTMLInputElement).value })} />
        </div>
      ) : (
        <div class="chips wrapc" role="group" aria-label="How often">
          {FREQS.map(([f, label]) => (
            <button type="button" class="glass chip pk" aria-pressed={freq === f} onClick={() => { setFreq(f); props.onChange({ days: daysFor(f, props.days) }); }}>{label}</button>
          ))}
        </div>
      )}
      <TimeWheel value={props.time} onChange={(time) => props.onChange({ time })} />
      {props.kind === "repeat" && (freq === "custom" || freq === "weekly") && <DayChips days={props.days} onChange={(days) => props.onChange({ days })} />}
    </div>
  );
}

export function WizardHost() {
  const w = wizard.value;
  if (!w?.doc) return null;
  return <ScheduleMessage key={JSON.stringify(w).length} doc={w.doc} title={w.title} onClose={() => (wizard.value = null)} />;
}

/** The Schedule button on Create: schedule just this message. Everything else lives in Schedules. */
function ScheduleMessage(props: { doc: Doc; title?: string; onClose: () => void }) {
  const first = soon();
  const [kind, setKind] = useState<"once" | "repeat">("once");
  const [date, setDate] = useState(first.date);
  const [time, setTime] = useState(first.time);
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [name, setName] = useState(props.title || firstWords(props.doc) || "My message");
  const [busy, setBusy] = useState(false);
  const past = kind === "once" && atTime(date, time).getTime() <= Date.now();
  const summary = kind === "once" ? (past ? "That time has already passed." : `Prints once, ${onceText(date, time)}.`)
    : days.length ? `Prints ${whenText({ time, days }).replace(/^Every/, "every")}. ${firstRunText(time, days)}` : "Pick at least one day.";
  const save = async () => {
    setBusy(true);
    try {
      await send<Schedule>("POST", "/api/schedules", {
        name: name.trim() || "My message", time, enabled: true, conditions: [],
        days: kind === "once" ? [] : days, once: kind === "once" ? date : null,
        sections: [{ type: "message", document: props.doc }],
      });
      toast(kind === "once" ? `Scheduled for ${onceText(date, time)}` : `Scheduled ${whenText({ time, days }).toLowerCase()}`);
      schedulesChanged.value++;
      props.onClose();
    } catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={props.onClose} title="Schedule this message" tint="tp">
      <div class="stack">
        <div class="glass" style="border-radius:16px;padding:4px 4px 4px 14px;display:flex;align-items:center;gap:10px">
          <label for="smname" class="cap" style="color:var(--silver)">Name</label>
          <input id="smname" value={name} maxLength={60} onInput={(e) => setName((e.target as HTMLInputElement).value)} style="flex:1;min-width:0;height:44px;border:0;background:transparent;outline:none;font-size:16px;font-weight:600;color:var(--hi)" />
        </div>
        <Seg label="How often" value={kind} onChange={setKind} options={[{ value: "once", label: "Once" }, { value: "repeat", label: "Repeat" }]} />
        <WhenPicker kind={kind} date={date} time={time} days={days}
          onChange={(p) => { if (p.date !== undefined) setDate(p.date); if (p.time !== undefined) setTime(p.time); if (p.days !== undefined) setDays(p.days); }} />
        <div class="glass summary"><IconAlarm class="i" /><span>{summary}</span></div>
        <button class="btn-pink block" disabled={busy || past || (kind === "repeat" && !days.length)} onClick={save}>Save schedule</button>
        <p class="cap" style="margin:0 4px">Weather, calendar, routines and more: <a href="/schedules" onClick={props.onClose} style="color:var(--pink-text)">Schedules</a>.</p>
      </div>
    </Sheet>
  );
}

function firstWords(doc: Doc): string {
  for (const b of doc.blocks as any[]) {
    const t = (b.text ?? b.items?.[0]?.text ?? "").trim();
    if (t) return t.split("\n")[0].slice(0, 30);
  }
  return "";
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
const NEW_DRAFT = (): Schedule => ({ id: "", name: "New schedule", enabled: true, time: "07:30", days: [0, 1, 2, 3, 4, 5, 6], once: null,
  sections: [], conditions: [], next_run: null, last_run_at: null, last_result: null });

function Routine(props: { id: string; meta: ListResp | null; onDone: () => void }) {
  const { route } = useLocation();
  const draft = props.id === "new";
  const [s, setS] = useState<Schedule | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [pv, setPv] = useState<string | null>(null);
  const [named, setNamed] = useState(!draft);
  useEffect(() => {
    if (draft) { setS(NEW_DRAFT()); setNamed(false); return; }
    get<Schedule>(`/api/schedules/${props.id}`).then(setS).catch(props.onDone);
  }, [props.id]);
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
  const body = () => ({ name: s.name, time: s.time, days: s.once ? [] : s.days, once: s.time ? s.once ?? null : null,
    sections: s.sections, conditions: s.conditions, enabled: s.once ? true : s.enabled });
  const check = () => {
    if (!s.sections.length) return "Add a block first.";
    if (s.sections.some((x) => x.type === "countdown" && !x.date)) return "Pick a date for the countdown.";
    if (s.time && s.once && atTime(s.once, s.time).getTime() <= Date.now()) return "That date and time has already passed.";
    if (s.time && !s.once && !s.days.length) return "Pick at least one day.";
    return null;
  };
  const save = async () => {
    const why = check();
    if (why) return toast(why);
    try {
      if (draft) await send<Schedule>("POST", "/api/schedules", body());
      else await send("PATCH", `/api/schedules/${s.id}`, body());
      schedulesChanged.value++;
      toast(s.time ? (s.once ? `Scheduled for ${onceText(s.once, s.time)}` : `Scheduled for ${s.time}`) : "Saved");
      props.onDone();
    } catch (e) { toast((e as Error).message); }
  };
  const printNow = async () => {
    try {
      let id = s.id;
      if (draft) { // save it first so it can run, then keep editing the saved one
        const why = check();
        if (why) return toast(why);
        id = (await send<Schedule>("POST", "/api/schedules", body())).id;
        schedulesChanged.value++;
        route(`/schedules/${id}`, true);
      }
      toast((await send<{ message: string }>("POST", `/api/schedules/${id}/run`)).message);
    } catch (e) { toast((e as Error).message); }
  };
  const kind: "repeat" | "once" | "none" = !s.time ? "none" : s.once ? "once" : "repeat";
  const setKind = (k: "repeat" | "once" | "none") => {
    if (k === "none") set({ time: null, once: null });
    else if (k === "once") {
      const f = soon();
      const keep = s.time && s.once && atTime(s.once, s.time).getTime() > Date.now();
      set(keep ? {} : { time: f.time, once: f.date });
    }
    else set({ time: s.time ?? "07:30", once: null, days: s.days.length ? s.days : [0, 1, 2, 3, 4, 5, 6] });
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
      <Topbar title={draft ? "New schedule" : s.name || "Routine"} back={props.onDone} backLabel="Schedules"><StatusPill /></Topbar>
      <div class="glass" style="border-radius:16px;padding:4px 4px 4px 14px;display:flex;align-items:center;gap:10px">
        <label for="sname" class="cap" style="color:var(--silver)">Name</label>
        <input id="sname" value={s.name} maxLength={60} onInput={(e) => { setNamed(true); set({ name: (e.target as HTMLInputElement).value }); }} style="flex:1;min-width:0;height:44px;border:0;background:transparent;outline:none;font-size:16px;font-weight:600;color:var(--hi)" />
      </div>
      {draft && s.sections.length === 0 && (
        <>
          <span class="sect">Start from</span>
          <div class="chips wrapc" role="group" aria-label="Start from">
            {STARTERS.map((st) => (
              <button class="glass chip pk" onClick={() => set({ sections: st.sections.map((x) => ({ ...x })), ...(named ? {} : { name: st.defName }) })}>
                <st.Icon class="i" />{st.name}
              </button>
            ))}
          </div>
        </>
      )}

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
      {s.sections.some((x) => x.type === "agenda" || x.type === "tasks") && <GoogleHint />}

      <span class="sect">When</span>
      <div class="glass card stack">
        <Seg label="When" value={kind} onChange={setKind}
          options={[{ value: "repeat", label: "Repeat" }, { value: "once", label: "Once" }, { value: "none", label: "No set time" }]} />
        {s.time && (
          <WhenPicker kind={kind === "once" ? "once" : "repeat"} date={s.once ?? soon().date} time={s.time} days={s.days}
            onChange={(p) => set({ ...(p.time !== undefined ? { time: p.time } : {}), ...(p.days !== undefined ? { days: p.days } : {}), ...(p.date !== undefined ? { once: p.date } : {}) })} />
        )}
        <p class="cap">{!s.time ? "Without a time, run it from the arcade button or a quick chip on Create."
          : s.once ? `Prints once, ${onceText(s.once, s.time)}, then switches off.` : `${whenText(s)}. ${firstRunText(s.time, s.days)}`}</p>
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
        <div class="rwrap" style="width:100%;max-width:384px">{s.sections.length ? <div class="receipt bits img">{pv ? <img src={pv} alt="What it will print today" /> : <div class="shim" style="height:180px;margin:0 10px" />}</div> : <p class="cap">Add a block to see it.</p>}</div>
      </div>
      <div class="actrow">
        <button class="btn-green" style="flex:1" disabled={!s.sections.length} onClick={printNow}>Print now</button>
        <button class="btn-pink" style="flex:1" disabled={!s.sections.length} onClick={save}>{s.time ? "Save schedule" : "Save routine"}</button>
      </div>
      {!draft && <button class="btn btn-danger" onClick={() => setConfirmDel(true)}><IconTrash class="i" />Delete</button>}

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
