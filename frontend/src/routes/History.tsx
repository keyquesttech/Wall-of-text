import { useEffect, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { api, type Job } from "../lib/api";
import { lastJobEvent, trackJob } from "../lib/state";
import { IconHistory, IconRefresh, IconTrash } from "../components/icons";
import { moment, StatusPill } from "../components/printer";
import { Banner, Sheet, timeAgo, toast, Topbar } from "../components/ui";

const FILTERS = [
  { id: "", label: "All" },
  { id: "Manual", label: "Manual" },
  { id: "Schedule", label: "Schedules" },
  { id: "Button", label: "Button" },
  { id: "Guest", label: "Guest" },
  { id: "Remote", label: "Remote" },
];

const STATE_LABEL: Record<string, string> = {
  done: "Printed", failed: "Failed", cancelled: "Cancelled", missed: "Missed", printing: "Printing", queued: "Waiting", held: "Held",
};

export function History() {
  const { params } = useRoute();
  const { route } = useLocation();
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<Job[]>([]);
  const [more, setMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = async (reset = true) => {
    setLoading(true);
    try {
      const before = reset ? undefined : items[items.length - 1]?.id;
      const r = await api.history(filter || undefined, before);
      setItems(reset ? r.items : [...items, ...r.items]);
      setMore(r.items.length >= 40);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(true); }, [filter]);
  // live updates: merge job events into the list
  useEffect(() => {
    const j = lastJobEvent.value;
    if (!j || (filter && j.source !== filter)) return;
    setItems((xs) => {
      const i = xs.findIndex((x) => x.id === j.id);
      if (i >= 0) { const c = xs.slice(); c[i] = { ...c[i], ...j }; return c; }
      return [j, ...xs];
    });
  }, [lastJobEvent.value]);

  const openId = params.id ? Number(params.id) : null;
  return (
    <>
      <Topbar title="History"><StatusPill /></Topbar>
      <div class="chips" role="group" aria-label="Filter">
        {FILTERS.map((f) => (
          <button class="chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>
        ))}
      </div>
      {items.length === 0 && !loading && (
        <div class="empty"><IconHistory /><p>Nothing here yet.</p><a class="btn" href="/">Make something</a></div>
      )}
      {items.length > 0 && (
        <div class="glass list" style="margin-top:10px">
          {items.map((j) => (
            <a class="lrow" href={`/history/${j.id}`}>
              {j.has_image ? <img class="thumb" src={`/api/history/${j.id}/image`} alt="" loading="lazy" /> : <span class="thumb ph"><IconHistory width={20} /></span>}
              <div class="grow">
                <div class="title">{j.title}</div>
                <div class="sub">{j.source} · {timeAgo(j.created_at)}{j.copies > 1 ? ` · ×${j.copies}` : ""}</div>
              </div>
              {j.state !== "done" && <span class={`state-tag ${j.state}`}>{STATE_LABEL[j.state] ?? j.state}</span>}
            </a>
          ))}
        </div>
      )}
      <div class="row" style="margin-top:14px;justify-content:center">
        {more && items.length > 0 && <button class="btn" disabled={loading} onClick={() => load(false)}>Show older</button>}
        {items.length > 0 && <button class="btn btn-ghost btn-danger" onClick={() => setConfirmClear(true)}>Clear history</button>}
      </div>
      <Sheet open={confirmClear} onClose={() => setConfirmClear(false)} title="Clear history?">
        <p>This removes every finished print from History. Prints in the queue stay.</p>
        <div class="stack">
          <button class="btn btn-pink" onClick={async () => { await api.clearHistory(); setConfirmClear(false); load(true); toast("History cleared"); }}>Clear history</button>
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
  if (j.error === "interrupted") return "The printer stopped part-way through, so this didn't finish. It won't reprint by itself.";
  if (j.error?.startsWith("offline")) return "The printer went offline while printing.";
  return j.error || "This didn't print.";
}

function Detail(props: { id: number; onClose: () => void; onChanged: () => void }) {
  const [j, setJ] = useState<(Job & { document: any }) | null>(null);
  useEffect(() => { api.historyItem(props.id).then(setJ).catch(() => props.onClose()); }, [props.id]);
  const again = async (fn: () => Promise<{ job: Job }>) => {
    const r = await fn();
    trackJob(r.job);
    moment.value = { job: r.job, img: j?.has_image ? `/api/history/${props.id}/image` : null };
    props.onClose();
  };
  const err = j ? errorText(j) : null;
  return (
    <Sheet open onClose={props.onClose} title={j?.title ?? "…"}>
      {j && (
        <>
          <p class="dim small" style="margin-top:-4px">{j.source} · {timeAgo(j.created_at)} · {STATE_LABEL[j.state]}</p>
          {err && <Banner>{err}</Banner>}
          {j.has_image && (
            <div class="paper-wrap"><div class="paper"><img src={`/api/history/${j.id}/image`} alt={`What was printed: ${j.title}`} /></div></div>
          )}
          <div class="stack" style="margin-top:16px">
            {j.has_image && j.state === "failed" && <button class="btn btn-green" onClick={() => again(() => api.retry(j.id))}><IconRefresh width={18} />Try again</button>}
            {j.has_image && j.state !== "failed" && <button class="btn btn-green" onClick={() => again(() => api.reprint(j.id))}>Print again</button>}
            {!["printing", "queued", "held"].includes(j.state) && (
              <button class="btn btn-danger" onClick={async () => { await api.deleteHistory(j.id); props.onChanged(); props.onClose(); toast("Removed"); }}>
                <IconTrash width={18} />Remove from history
              </button>
            )}
          </div>
        </>
      )}
    </Sheet>
  );
}
