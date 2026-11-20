// Status pill + sheet, live "As printed" preview, and the print moment.
import { signal } from "@preact/signals";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, preview as fetchPreview, ApiError, type Doc, type Job, type Preview } from "../lib/api";
import { jobProgress, jobs, pendingJobs, printer, trackJob, wifi } from "../lib/state";
import { IconPrinter, IconX } from "./icons";
import { Banner, Sheet, toast } from "./ui";

export const STATE_TEXT: Record<string, string> = {
  ready: "Ready",
  printing: "Printing",
  offline: "Printer offline",
  paper_out: "Out of paper",
};

export const statusOpen = signal(false);

export function StatusPill() {
  const p = printer.value;
  const state = p?.state ?? "ready";
  const q = p?.queue_length ?? 0;
  const label = state === "printing" && q > 1 ? `Printing · ${q - 1} waiting` : state !== "printing" && q > 0 ? `${STATE_TEXT[state]} · ${q} waiting` : STATE_TEXT[state];
  return (
    <button class="pill" onClick={() => (statusOpen.value = true)} aria-label={`Printer status: ${label}. Open details`}>
      <span class={`dot ${state}`} aria-hidden="true" />
      {label}
    </button>
  );
}

export function StatusSheet() {
  const p = printer.value;
  const w = wifi.value;
  const pend = pendingJobs.value;
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    try { await fn(); toast(msg); } catch (e) { toast((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Sheet open={statusOpen.value} onClose={() => (statusOpen.value = false)} title="Printer">
      {p?.state === "offline" && (
        <Banner>The printer isn't answering. Check its power and USB cable. Prints wait in the queue until it's back.</Banner>
      )}
      {p?.state === "paper_out" && (
        <Banner action={<button class="btn small" disabled={busy} onClick={() => act(api.newRoll, "New roll noted")}>New roll loaded</button>}>
          Out of paper. Prints wait in the queue.
        </Banner>
      )}
      <div class="glass list">
        <div class="lrow kv-row"><span class="grow">Status</span><span class="meta">{STATE_TEXT[p?.state ?? "ready"]}</span></div>
        <div class="lrow kv-row"><span class="grow">Paper</span><span class="meta">About {p?.paper_percent ?? 100}% left</span></div>
        <div class="lrow kv-row"><span class="grow">Wi-Fi</span><span class="meta">{w?.ssid ?? "—"}</span></div>
        <div class="lrow kv-row"><span class="grow">Address</span><span class="meta mono">{w?.hostname}{w?.ip ? ` · ${w.ip}` : ""}</span></div>
      </div>
      <h2 class="section">Queue</h2>
      <div class="glass list">
        {pend.length === 0 && <div class="lrow dim">Nothing waiting.</div>}
        {pend.map((j) => <QueueRow job={j} />)}
      </div>
      <div class="stack" style="margin-top:14px">
        {pend.length > 1 && <button class="btn btn-danger" disabled={busy} onClick={() => act(api.cancelAll, "Queue cleared")}>Cancel all</button>}
        <div class="row">
          <button class="btn grow" disabled={busy} onClick={() => act(api.testPage, "Printing a test page")}>Test page</button>
          {p?.state !== "paper_out"
            ? <button class="btn grow" disabled={busy} onClick={() => act(() => api.paperOut(true), "Marked as out of paper")}>Out of paper</button>
            : <button class="btn grow" disabled={busy} onClick={() => act(api.newRoll, "New roll noted")}>New roll</button>}
        </div>
        <button class="btn" disabled={busy} onClick={() => act(api.newRoll, "Paper counter reset")}>I loaded a new roll</button>
      </div>
    </Sheet>
  );
}

function QueueRow({ job }: { job: Job }) {
  const pct = jobProgress(job.id);
  return (
    <div class="lrow">
      <div class="grow">
        <div class="title">{job.title}</div>
        <div class="sub">
          {job.state === "printing" ? `Printing · ${pct}%` : job.state === "held" ? `Held for quiet hours` : "Waiting"} · {job.source}
        </div>
        {job.state === "printing" && <div class="progress" style="margin-top:6px"><i style={{ width: `${pct}%` }} /></div>}
      </div>
      <button class="icon-btn" aria-label={`Cancel ${job.title}`} onClick={() => api.cancel(job.id).then(() => toast("Cancelled"))}>
        <IconX />
      </button>
    </div>
  );
}

// --------------------------------------------------------------- preview --
export function usePreview(doc: Doc, delay = 250) {
  const [pv, setPv] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = JSON.stringify(doc);
  useEffect(() => {
    const ctl = new AbortController();
    setLoading(true);
    const t = window.setTimeout(async () => {
      try {
        const p = await fetchPreview(doc, ctl.signal);
        setPv((old) => { if (old) URL.revokeObjectURL(old.url); return p; });
        setError(null);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      } finally {
        if (!ctl.signal.aborted) setLoading(false);
      }
    }, delay);
    return () => { ctl.abort(); window.clearTimeout(t); };
  }, [key]);
  return { pv, loading, error };
}

export function AsPrinted(props: { doc: Doc; compact?: boolean }) {
  const { pv, loading, error } = usePreview(props.doc);
  return (
    <section aria-label="As printed">
      <div class="paper-wrap">
        <div class={`paper ${loading ? "loading" : ""}`}>
          {pv ? <img src={pv.url} alt="Preview of the printed slip" /> : <div style="height:120px" />}
        </div>
      </div>
      <div class="paper-meta">
        <span>As printed</span>
        <span>{pv ? `${Math.max(1, Math.round(pv.lengthMm / 10))} cm of paper` : ""}</span>
      </div>
      {error && <Banner>{error}</Banner>}
      {pv?.warnings.map((w) => <Banner kind="warn">{w}</Banner>)}
    </section>
  );
}

// ---------------------------------------------------------- print moment --
interface Moment { job: Job; img: string | null; }
export const moment = signal<Moment | null>(null);

export async function printWithMoment(doc: Doc, title?: string, copies = 1): Promise<Job | null> {
  let img: string | null = null;
  try {
    img = (await fetchPreview(doc)).url;
  } catch { /* the print call reports errors */ }
  try {
    const r = await api.print(doc, copies, title);
    trackJob(r.job);
    moment.value = { job: r.job, img };
    return r.job;
  } catch (e) {
    toast(e instanceof ApiError ? e.message : "Couldn't print. Try again.");
    return null;
  }
}

export function PrintMoment() {
  const m = moment.value;
  const ref = useRef<HTMLDivElement>(null);
  if (!m) return null;
  const job = jobs.value.get(m.job.id) ?? m.job;
  const pct = jobProgress(job.id);
  const st = printer.value?.state;
  const done = job.state === "done";
  const failed = job.state === "failed" || job.state === "cancelled";
  const waiting = job.state === "queued" || job.state === "held";
  const ahead = pendingJobs.value.filter((j) => j.id < job.id).length;
  const shown = done ? 100 : job.state === "printing" ? Math.max(4, pct) : 0;
  let text = "Printing…";
  let sub = "";
  if (done) { text = "Printed"; sub = "Tear it off and stick it up."; }
  else if (failed) { text = job.state === "cancelled" ? "Cancelled" : "Didn't print"; sub = job.error === "interrupted" ? "The printer stopped part-way." : "You can try again from History."; }
  else if (waiting && st === "offline") { text = "Waiting for the printer"; sub = "It's offline. This prints as soon as it's back."; }
  else if (waiting && st === "paper_out") { text = "Out of paper"; sub = "Load a new roll and this prints straight away."; }
  else if (job.state === "held") { text = "Held for quiet hours"; sub = "It prints when quiet hours end."; }
  else if (waiting) { text = ahead ? `In the queue · ${ahead} ahead` : "Starting…"; }
  const close = () => (moment.value = null);
  return (
    <div class={`pm ${done ? "pm-done" : ""}`} role="dialog" aria-modal="true" aria-label="Printing" onClick={(e) => e.target === e.currentTarget && close()}>
      <div class="pm-printer"><span class={`pm-led ${done ? "done" : failed ? "bad" : ""}`} /></div>
      <div class="pm-slot" ref={ref}>
        <div class="pm-paper" style={{ clipPath: `inset(0 0 ${100 - shown}% 0)` }}>
          {m.img ? <img src={m.img} alt="" /> : <div style="height:160px" />}
        </div>
      </div>
      <div class="pm-text" aria-live="polite">{text}</div>
      {sub && <div class="pm-sub">{sub}</div>}
      <div class="pm-actions">
        {!done && !failed && <button class="btn" onClick={() => api.cancel(job.id).then(close)}>Cancel</button>}
        {failed && job.state === "failed" && <button class="btn" onClick={() => api.retry(job.id).then((r) => { trackJob(r.job); moment.value = { job: r.job, img: m.img }; })}>Try again</button>}
        <button class={`btn ${done ? "btn-green" : ""}`} onClick={close}>{done ? "Done" : "Close"}</button>
      </div>
    </div>
  );
}

export function PrinterBadge() {
  return <IconPrinter />;
}

export function PrinterBanner() {
  const p = printer.value;
  if (p?.state === "offline")
    return <Banner action={<button class="btn small" onClick={() => (statusOpen.value = true)}>Details</button>}>The printer is offline. Prints wait in the queue until it's back.</Banner>;
  if (p?.state === "paper_out")
    return <Banner action={<button class="btn small" onClick={() => api.newRoll().then(() => toast("New roll noted"))}>New roll</button>}>Out of paper. Prints wait in the queue.</Banner>;
  if (p && p.paper_percent <= 10)
    return <Banner kind="warn">Paper is running low (about {p.paper_percent}% left).</Banner>;
  return null;
}
