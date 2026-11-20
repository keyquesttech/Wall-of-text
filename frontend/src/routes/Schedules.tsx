import { useEffect, useMemo, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { get, send, type Preview } from "../lib/api";
import { settings } from "../lib/state";
import { IconClock, IconDown, IconPlus, IconTrash, IconUp } from "../components/icons";
import { StatusPill } from "../components/printer";
import { Banner, Sheet, timeAgo, toast, Toggle, ToggleRow, Topbar } from "../components/ui";

export interface Section { type: string; [k: string]: any }
export interface Condition { type: string; value?: number }
export interface Schedule {
  id: string; name: string; enabled: boolean; time: string | null; days: number[];
  sections: Section[]; conditions: Condition[]; next_run: number | null; last_run_at: number | null; last_result: string | null;
}
interface ListResp { items: Schedule[]; status: { clock_synced: boolean; holiday_mode: boolean; quiet_now: boolean; timezone: string }; sections: Record<string, string>; conditions: Record<string, string> }

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const STARTERS: { name: string; desc: string; time: string | null; sections: Section[]; conditions?: Condition[] }[] = [
  { name: "Morning briefing", desc: "Date, weather, today's calendar and to-dos", time: "07:00", sections: [{ type: "date" }, { type: "weather" }, { type: "agenda" }, { type: "tasks" }, { type: "fortune" }] },
  { name: "Umbrella alert", desc: "Weather, only when rain is likely", time: "07:30", sections: [{ type: "weather" }], conditions: [{ type: "rain_above", value: 60 }] },
  { name: "Daily fortune", desc: "A little line to start the day", time: "08:00", sections: [{ type: "fortune" }] },
  { name: "Countdown", desc: "Days until something good", time: "08:00", sections: [{ type: "countdown", date: "", label: "" }] },
  { name: "Shopping list", desc: "Prints the shared list (if it has items)", time: "17:30", sections: [{ type: "shopping", skip_empty: true }] },
  { name: "Custom routine", desc: "Start empty and add sections", time: null, sections: [] },
];

function daysLabel(d: number[]) {
  if (d.length === 7) return "Every day";
  if (d.join() === "0,1,2,3,4") return "Weekdays";
  if (d.join() === "5,6") return "Weekends";
  return d.map((x) => DAYS[x]).join(" ");
}

function nextLabel(ts: number | null) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return `Next: today ${hm}`;
  const t = new Date(now.getTime() + 86400000);
  if (d.toDateString() === t.toDateString()) return `Next: tomorrow ${hm}`;
  return `Next: ${d.toLocaleDateString("en-GB", { weekday: "short" })} ${hm}`;
}

export function Schedules() {
  const { params } = useRoute();
  const { route } = useLocation();
  const [data, setData] = useState<ListResp | null>(null);
  const [pick, setPick] = useState(false);
  const load = () => get<ListResp>("/api/schedules").then(setData);
  useEffect(() => { load(); }, [params.id]);

  if (params.id) return <Editor id={params.id} meta={data} onDone={() => { route("/schedules"); load(); }} />;
  const st = data?.status;
  const holiday = !!settings.value?.schedules?.holiday_mode;
  const timed = data?.items.filter((s) => s.time) ?? [];
  const routines = data?.items.filter((s) => !s.time) ?? [];
  return (
    <>
      <Topbar title="Schedules"><StatusPill /></Topbar>
      {st && !st.clock_synced && <Banner>Waiting for the clock. The printer sets its clock from the internet after a power cut; schedules start once it has.</Banner>}
      {holiday && <Banner kind="warn">Holiday mode is on. No schedules will print.</Banner>}
      {st?.quiet_now && !holiday && <Banner kind="info">Quiet hours now. Scheduled prints wait until they end.</Banner>}
      <div class="glass list">
        <ToggleRow label="Holiday mode" sub="Pause every schedule" checked={holiday}
          onChange={(v) => send("PATCH", "/api/settings", { schedules: { holiday_mode: v } }).then((s) => (settings.value = s))} />
      </div>
      <h2 class="section">Scheduled</h2>
      {timed.length === 0 && <div class="empty"><IconClock /><p>Nothing scheduled yet.</p></div>}
      {timed.length > 0 && (
        <div class="glass list">
          {timed.map((s) => <Row s={s} onToggle={load} />)}
        </div>
      )}
      {routines.length > 0 && (
        <>
          <h2 class="section">Routines (button and quick actions only)</h2>
          <div class="glass list">{routines.map((s) => <Row s={s} onToggle={load} />)}</div>
        </>
      )}
      <button class="btn btn-green block" style="margin-top:18px" onClick={() => setPick(true)}><IconPlus width={18} />New schedule</button>
      <Sheet open={pick} onClose={() => setPick(false)} title="Start from">
        <div class="glass list">
          {STARTERS.map((st) => (
            <button class="lrow" onClick={async () => {
              const s = await send<Schedule>("POST", "/api/schedules", { name: st.name, time: st.time, sections: st.sections, conditions: st.conditions ?? [], days: [0, 1, 2, 3, 4, 5, 6], enabled: true });
              setPick(false);
              route(`/schedules/${s.id}`);
            }}>
              <div class="grow"><div class="title">{st.name}</div><div class="sub">{st.desc}</div></div>
            </button>
          ))}
        </div>
      </Sheet>
    </>
  );
}

function Row({ s, onToggle }: { s: Schedule; onToggle: () => void }) {
  let last = "";
  try {
    const r = s.last_result ? JSON.parse(s.last_result) : null;
    if (r && s.last_run_at) last = `${r.state === "printed" ? "Printed" : r.state === "held" ? "Held" : r.state === "skipped" ? "Skipped" : "Missed"} ${timeAgo(s.last_run_at)}`;
  } catch { /* ignore */ }
  return (
    <div class="lrow">
      <a class="grow" href={`/schedules/${s.id}`} style="color:inherit;text-decoration:none;min-width:0">
        <div class="title">{s.time ? `${s.time} · ` : ""}{s.name}</div>
        <div class="sub">{s.time ? daysLabel(s.days) : `${s.sections.length} section${s.sections.length === 1 ? "" : "s"}`}{s.enabled && s.next_run ? ` · ${nextLabel(s.next_run)}` : ""}{last ? ` · ${last}` : ""}</div>
      </a>
      {s.time && <Toggle label={`${s.name} on`} checked={s.enabled} onChange={(v) => send("PATCH", `/api/schedules/${s.id}`, { enabled: v }).then(onToggle)} />}
    </div>
  );
}

// ------------------------------------------------------------- editor --
function Editor(props: { id: string; meta: ListResp | null; onDone: () => void }) {
  const [s, setS] = useState<Schedule | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [pv, setPv] = useState<Preview | null>(null);
  const [pvBusy, setPvBusy] = useState(false);
  useEffect(() => { get<Schedule>(`/api/schedules/${props.id}`).then(setS).catch(props.onDone); }, [props.id]);
  const set = (p: Partial<Schedule>) => setS((x) => (x ? { ...x, ...p } : x));
  const key = useMemo(() => JSON.stringify(s?.sections ?? []), [s?.sections]);
  useEffect(() => { setPv(null); }, [key]);
  if (!s) return <div class="empty"><div class="spinner" style="margin:auto" /></div>;
  const secNames = props.meta?.sections ?? {};
  const condNames = props.meta?.conditions ?? {};
  const save = async () => {
    if (s.sections.some((x) => x.type === "countdown" && !x.date)) return toast("Pick a date for the countdown.");
    await send("PATCH", `/api/schedules/${s.id}`, { name: s.name, time: s.time, days: s.days, sections: s.sections, conditions: s.conditions, enabled: s.enabled });
    toast("Saved");
    props.onDone();
  };
  const preview = async () => {
    setPvBusy(true);
    try {
      const r = await fetch("/api/schedules/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sections: s.sections }) });
      if (!r.ok) throw new Error("Preview failed");
      setPv({ url: URL.createObjectURL(await r.blob()), rows: 0, lengthMm: Number(r.headers.get("X-Wot-Length-Mm")), coverage: 0, warnings: [] });
    } catch (e) { toast((e as Error).message); } finally { setPvBusy(false); }
  };
  const move = (i: number, d: number) => {
    const xs = s.sections.slice();
    const j = i + d;
    if (j < 0 || j >= xs.length) return;
    [xs[i], xs[j]] = [xs[j], xs[i]];
    set({ sections: xs });
  };
  const updSec = (i: number, p: Partial<Section>) => set({ sections: s.sections.map((x, k) => (k === i ? { ...x, ...p } : x)) });
  return (
    <>
      <Topbar title={s.name || "Schedule"} back={props.onDone} />
      <label class="field-label" for="sname">Name</label>
      <input id="sname" class="input" value={s.name} maxLength={60} onInput={(e) => set({ name: (e.target as HTMLInputElement).value })} />

      <h2 class="section">When</h2>
      <div class="glass card">
        <div class="row" style="justify-content:space-between">
          <span>Print at a set time</span>
          <Toggle label="Print at a set time" checked={!!s.time} onChange={(v) => set({ time: v ? "07:00" : null })} />
        </div>
        {s.time && (
          <>
            <input type="time" class="input" style="margin-top:12px;font-size:22px" value={s.time} aria-label="Time"
              onInput={(e) => set({ time: (e.target as HTMLInputElement).value || "07:00" })} />
            <div class="chips" role="group" aria-label="Days" style="margin-top:12px;flex-wrap:wrap">
              {DAYS.map((d, i) => (
                <button class="chip" aria-pressed={s.days.includes(i)} onClick={() => set({ days: s.days.includes(i) ? s.days.filter((x) => x !== i) : [...s.days, i].sort() })}>{d}</button>
              ))}
            </div>
          </>
        )}
        {!s.time && <p class="dim small" style="margin:10px 0 0">Without a time this is a routine you run from the button or a quick action.</p>}
      </div>

      <h2 class="section">What to print</h2>
      <div class="glass list">
        {s.sections.length === 0 && <div class="lrow dim">No sections yet.</div>}
        {s.sections.map((sec, i) => (
          <div class="lrow" style="flex-wrap:wrap">
            <div class="grow"><div class="title">{secNames[sec.type] ?? sec.type}</div></div>
            <button class="icon-btn" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><IconUp /></button>
            <button class="icon-btn" aria-label="Move down" disabled={i === s.sections.length - 1} onClick={() => move(i, 1)}><IconDown /></button>
            <button class="icon-btn" aria-label={`Remove ${secNames[sec.type]}`} onClick={() => set({ sections: s.sections.filter((_, k) => k !== i) })}><IconTrash /></button>
            {sec.type === "quote" && (
              <textarea class="input" style="min-height:70px;margin-top:8px" placeholder="Your line" value={sec.text ?? ""} maxLength={400}
                onInput={(e) => updSec(i, { text: (e.target as HTMLTextAreaElement).value })} />
            )}
            {sec.type === "countdown" && (
              <div class="row" style="width:100%;margin-top:8px">
                <input class="input grow" placeholder="What (e.g. Holiday)" value={sec.label ?? ""} maxLength={40} onInput={(e) => updSec(i, { label: (e.target as HTMLInputElement).value })} />
                <input class="input" type="date" style="width:170px" value={sec.date ?? ""} aria-label="Date" onInput={(e) => updSec(i, { date: (e.target as HTMLInputElement).value })} />
              </div>
            )}
          </div>
        ))}
        <button class="lrow" onClick={() => setAdding(true)}><IconPlus width={18} /><span class="grow">Add a section</span></button>
      </div>

      {s.time && (
        <>
          <h2 class="section">Only print if…</h2>
          <div class="glass list">
            {s.conditions.map((c, i) => (
              <div class="lrow">
                <span class="grow">{condNames[c.type] ?? c.type}</span>
                {c.value !== undefined && (
                  <input class="input" type="number" style="width:90px" value={c.value} aria-label="Value"
                    onInput={(e) => set({ conditions: s.conditions.map((x, k) => (k === i ? { ...x, value: Number((e.target as HTMLInputElement).value) } : x)) })} />
                )}
                <span class="dim small">{c.type === "rain_above" ? "%" : c.type.startsWith("temp") ? "°" : ""}</span>
                <button class="icon-btn" aria-label="Remove condition" onClick={() => set({ conditions: s.conditions.filter((_, k) => k !== i) })}><IconTrash /></button>
              </div>
            ))}
            {s.conditions.length < 3 && (
              <div class="lrow">
                <select class="input" aria-label="Add a condition" value="" onChange={(e) => {
                  const t = (e.target as HTMLSelectElement).value;
                  if (!t) return;
                  const value = t === "rain_above" ? 50 : t === "temp_below" ? 3 : t === "temp_above" ? 22 : undefined;
                  set({ conditions: [...s.conditions, { type: t, ...(value !== undefined ? { value } : {}) }] });
                }}>
                  <option value="">Add a condition…</option>
                  {Object.entries(condNames).map(([k, v]) => <option value={k}>{v}</option>)}
                </select>
              </div>
            )}
          </div>
          <p class="dim tiny" style="margin:8px 6px">If the data isn't available when it's time, it prints anyway with a short note.</p>
        </>
      )}

      <div class="row" style="margin-top:18px">
        <button class="btn grow" disabled={pvBusy || s.sections.length === 0} onClick={preview}>{pvBusy ? "Making preview…" : "Preview"}</button>
        <button class="btn grow" disabled={s.sections.length === 0} onClick={() => send<{ message: string }>("POST", `/api/schedules/${s.id}/run`).then((r) => toast(r.message))}>Print now</button>
      </div>
      {pv && <div class="paper-wrap"><div class="paper"><img src={pv.url} alt="Preview" /></div></div>}
      <button class="btn btn-green block" style="margin-top:14px" onClick={save}>Save</button>
      <button class="btn btn-ghost btn-danger block" style="margin-top:8px" onClick={() => setConfirmDel(true)}>Delete</button>

      <Sheet open={adding} onClose={() => setAdding(false)} title="Add a section">
        <div class="glass list">
          {Object.entries(secNames).map(([k, v]) => (
            <button class="lrow" onClick={() => { set({ sections: [...s.sections, k === "countdown" ? { type: k, date: "", label: "" } : k === "quote" ? { type: k, text: "" } : { type: k }] }); setAdding(false); }}>{v}</button>
          ))}
        </div>
      </Sheet>
      <Sheet open={confirmDel} onClose={() => setConfirmDel(false)} title={`Delete “${s.name}”?`}>
        <div class="stack">
          <button class="btn btn-pink" onClick={() => send("DELETE", `/api/schedules/${s.id}`).then(() => { toast("Deleted"); props.onDone(); })}>Delete</button>
          <button class="btn" onClick={() => setConfirmDel(false)}>Cancel</button>
        </div>
      </Sheet>
    </>
  );
}
