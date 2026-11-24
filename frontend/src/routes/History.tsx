// History (HANDOFF 7.5, reference History.dc.html).
import { useEffect, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { api, send, type Job } from "../lib/api";
import { lastJobEvent, pendingJobs } from "../lib/state";
import { IconAlert, IconBookmark, IconHistory, IconPrint2, IconRefresh, IconSearch, IconTrash } from "../components/icons";
import { QueueCard, startMoment, StatusPill } from "../components/printer";
import { Banner, Sheet, timeAgo, toast, Topbar } from "../components/ui";

const FILTERS = [
  { id: "", label: "All" }, { id: "Manual", label: "Manual" }, { id: "Schedule", label: "Schedules" },
  { id: "Button", label: "Button" }, { id: "Guest", label: "Guest" }, { id: "Remote", label: "Remote" },
];
const DONE_STATES = ["done", "failed", "cancelled", "missed"];

function failText(j: Job): string {
  if (j.state === "missed") return j.error?.startsWith("Skipped") ? "Skipped" : "Missed";
  if (j.state === "cancelled") return "Cancelled";
  if (j.error === "paper_out") return "Paper ran out";
  if (j.error === "interrupted") return "Stopped part-way";
  if (j.error?.startsWith("offline")) return "Printer went offline";
  return "Didn't print";
}

export function History() {
  const { params } = useRoute();
  const { route } = useLocation();
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Job[] | null>(null);
  const [more, setMore] = useState(true);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = async (reset = true) => {
    const before = reset ? undefined : items?.[items.length - 1]?.id;
    const r = await api.history(filter || undefined, before, q.trim() || undefined);
    const got = r.items.filter((j) => DONE_STATES.includes(j.state));
    setItems(reset ? got : [...(items ?? []), ...got]);
    setMore(r.items.length >= 40);
  };
  useEffect(() => { const t = window.setTimeout(() => load(true), q ? 300 : 0); return () => window.clearTimeout(t); }, [filter, q]);
  useEffect(() => {
    const j = lastJobEvent.value;
    if (!j || !DONE_STATES.includes(j.state) || (filter && j.source !== filter) || q) return;
    setItems((xs) => {
      if (!xs) return xs;
      const i = xs.findIndex((x) => x.id === j.id);
      if (i >= 0) { const c = xs.slice(); c[i] = { ...c[i], ...j }; return c; }
      return [j, ...xs];
    });
  }, [lastJobEvent.value]);

  const waiting = pendingJobs.value.filter((j) => !filter || j.source === filter);
  const openId = params.id ? Number(params.id) : null;
  return (
    <>
      <Topbar title="History"><StatusPill /></Topbar>
      <div class="glass search">
        <IconSearch class="i" />
        <label class="sr-only" for="hs">Search prints</label>
        <input id="hs" type="search" placeholder="Search prints" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
      </div>
      <div class="chips" role="group" aria-label="Filter">
        {FILTERS.map((f) => <button class="glass chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>)}
      </div>

      {items === null && (
        <div class="stack" aria-busy="true" aria-label="Loading history">
          <div class="shim" style="height:70px;border-radius:20px" />
          <div class="hgrid"><div class="shim" style="height:150px;border-radius:18px" /><div class="shim" style="height:150px;border-radius:18px" /><div class="shim" style="height:150px;border-radius:18px" /><div class="shim" style="height:150px;border-radius:18px" /></div>
        </div>
      )}

      {waiting.length > 0 && (
        <>
          <span class="sect">Waiting · {waiting.length}</span>
          {waiting.map((j) => <QueueCard job={j} />)}
        </>
      )}

      {items && items.length === 0 && waiting.length === 0 && (
        <div class="empty"><IconHistory /><h2 class="h2">{q ? "Nothing matches" : "Nothing printed yet"}</h2>{!q && <a class="btn-green" href="/">Make something</a>}</div>
      )}
      {items && items.length > 0 && (
        <>
          <span class="sect">Printed</span>
          <div class="hgrid">
            {items.map((j) => {
              const bad = j.state !== "done";
              return (
                <a class={`glass hcard ${bad ? "bad" : ""}`} href={`/history/${j.id}`} aria-label={`${j.title}, ${timeAgo(j.created_at)}, ${j.source}${bad ? `, ${failText(j)}` : ""}`}>
                  <div class="rwrap"><div class="receipt bits">{j.has_image ? <img src={`/api/history/${j.id}/image`} alt="" loading="lazy" /> : <div class="r-c r-s" style="padding-top:20px">{j.title}</div>}</div></div>
                  {bad
                    ? <span class="warn"><IconAlert class="i" />{failText(j)}</span>
                    : <span class="t">{j.title}</span>}
                  <span class="cap" style="font-size:12px;margin-top:-6px">{bad ? j.title : `${timeAgo(j.created_at)} · ${j.source}`}</span>
                  {j.state === "failed" && j.has_image && (
                    <button class="btn" style="min-height:36px;font-size:13px" onClick={(e) => {
                      e.preventDefault();
                      api.retry(j.id).then((r) => { startMoment(r.job, null); toast("Printing again"); });
                    }}>Retry</button>
                  )}
                </a>
              );
            })}
          </div>
          <div class="row" style="justify-content:center;margin-top:4px">
            {more && <button class="btn" onClick={() => load(false)}>Show older</button>}
            <button class="btn btn-ghost btn-danger" onClick={() => setConfirmClear(true)}>Clear history</button>
          </div>
        </>
      )}
      <Sheet open={confirmClear} onClose={() => setConfirmClear(false)} title="Clear history?">
        <p>This removes every finished print from History. Prints in the queue stay.</p>
        <div class="stack">
          <button class="btn-pink" onClick={async () => { await api.clearHistory(); setConfirmClear(false); load(true); toast("History cleared"); }}>Clear history</button>
          <button class="btn" onClick={() => setConfirmClear(false)}>Cancel</button>
        </div>
      </Sheet>
      {openId && <Detail id={openId} onClose={() => route("/history")} onChanged={() => load(true)} />}
    </>
  );
}

function errorText(j: Job): string | null {
  if (j.state === "missed") return j.error || "Skipped because the printer was off.";
  if (j.state !== "failed") return null;
  if (j.error === "paper_out") return "Paper ran out part-way through. Load a new roll, then tap Try again.";
  if (j.error === "interrupted") return "The printer stopped part-way through, so this didn't finish. It won't reprint by itself.";
  if (j.error?.startsWith("offline")) return "The printer went offline while printing. Check its USB cable and power.";
  return j.error || "This didn't print.";
}

function Detail(props: { id: number; onClose: () => void; onChanged: () => void }) {
  const [j, setJ] = useState<(Job & { document: any }) | null>(null);
  const [saving, setSaving] = useState(false);
  const [tname, setTname] = useState("");
  useEffect(() => { api.historyItem(props.id).then((x) => { setJ(x); setTname(x.title); }).catch(() => props.onClose()); }, [props.id]);
  const again = async (fn: () => Promise<{ job: Job }>) => {
    const r = await fn();
    startMoment(r.job, j?.has_image ? `/api/history/${props.id}/image` : null);
    props.onClose();
  };
  const err = j ? errorText(j) : null;
  return (
    <Sheet open onClose={props.onClose} title={j?.title ?? "…"}>
      {j && (
        <div class="stack">
          <p class="cap" style="margin-top:-6px">{j.source} · {timeAgo(j.created_at)}</p>
          {err && <Banner>{err}</Banner>}
          {j.has_image && (
            <div style="display:flex;justify-content:center"><div class="rwrap" style="max-width:300px"><div class="receipt bits img"><img src={`/api/history/${j.id}/image`} alt={`What was printed: ${j.title}`} /></div></div></div>
          )}
          {j.has_image && j.state === "failed" && <button class="btn-green" onClick={() => again(() => api.retry(j.id))}><IconRefresh class="i" />Try again</button>}
          {j.has_image && j.state !== "failed" && <button class="btn-print block" onClick={() => again(() => api.reprint(j.id))}><IconPrint2 class="i" />Print again</button>}
          {j.document && !saving && <button class="btn" onClick={() => setSaving(true)}><IconBookmark class="i" />Save as template</button>}
          {saving && (
            <div class="row">
              <input class="input grow" aria-label="Template name" value={tname} maxLength={60} onInput={(e) => setTname((e.target as HTMLInputElement).value)} />
              <button class="btn-green" disabled={!tname.trim()} onClick={() => send("POST", "/api/templates", { name: tname.trim(), document: j.document }).then(() => { toast("Saved to Templates"); setSaving(false); })}>Save</button>
            </div>
          )}
          {!["printing", "queued", "held"].includes(j.state) && (
            <button class="btn btn-danger" onClick={async () => { await api.deleteHistory(j.id); props.onChanged(); props.onClose(); toast("Removed"); }}>
              <IconTrash class="i" />Remove from history
            </button>
          )}
        </div>
      )}
    </Sheet>
  );
}
