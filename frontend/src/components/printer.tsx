// Status pill + sheet, "As printed" receipt, print-moment state, printer-state banners.
import { signal } from "@preact/signals";
import { useEffect, useState } from "preact/hooks";
import { api, preview as fetchPreview, ApiError, type Doc, type Job, type Preview } from "../lib/api";
import { jobProgress, jobs, pendingJobs, printer, trackJob, wifi } from "../lib/state";
import { IconX } from "./icons";
import { Banner, Seg, Sheet, toast } from "./ui";

export const STATE_TEXT: Record<string, string> = {
  ready: "Online",
  printing: "Printing",
  offline: "Offline",
  paper_out: "Paper out",
};

export const statusOpen = signal(false);

export function StatusPill() {
  const p = printer.value;
  const state = p?.state ?? "ready";
  const waiting = Math.max(0, (p?.queue_length ?? 0) - (state === "printing" ? 1 : 0));
  const dot = state === "printing" ? "dot pulse" : state === "paper_out" ? "dot pink" : state === "offline" ? "dot grey" : "dot";
  return (
    <button class="glass pill" onClick={() => (statusOpen.value = true)}
      aria-label={`Printer ${STATE_TEXT[state]}, ${waiting} waiting. Open printer status`}>
      <span class={dot} aria-hidden="true" />{STATE_TEXT[state]}<span class="n">· {waiting} waiting</span>
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
  const pct = p?.paper_percent ?? 100;
  return (
    <Sheet open={statusOpen.value} onClose={() => (statusOpen.value = false)} title="Printer">
      <div class="stack">
        {p?.state === "offline" && <Banner>Printer is offline. Check its USB cable and power. Prints wait in the queue.</Banner>}
        {p?.state === "paper_out" && (
          <Banner action={<button class="btn" disabled={busy} onClick={() => act(api.newRoll, "New roll noted")} style="color:var(--pink-text)">Retry</button>}>
            Paper ran out. Load a new roll, then tap Retry.
          </Banner>
        )}
        <div class="glass grp">
          <div class="lrow"><span class={p?.state === "printing" ? "dot pulse" : p?.state === "paper_out" ? "dot pink" : p?.state === "offline" ? "dot grey" : "dot"} />{STATE_TEXT[p?.state ?? "ready"]}<span class="v num">{pend.length} waiting</span></div>
          <div class="lrow col"><div class="row" style="justify-content:space-between">Paper roll<span class="v num">About {pct}% left</span></div><div class={`bar ${pct <= 10 ? "pk" : ""}`}><i style={{ width: `${pct}%` }} /></div></div>
          <div class="lrow">Wi-Fi<span class="v">{w?.ssid ?? "—"}</span></div>
          <div class="lrow">Address<span class="v mono" style="font-size:13px">{w?.hostname}{w?.ip ? ` · ${w.ip}` : ""}</span></div>
        </div>
        {pend.length > 0 && (
          <>
            <span class="sect">Waiting · {pend.length}</span>
            {pend.map((j) => <QueueCard job={j} />)}
          </>
        )}
        <div class="row">
          <button class="btn-green grow" disabled={busy} onClick={() => act(api.testPage, "Printing a test page")}>Test print</button>
          <button class="btn grow" disabled={busy || pend.length === 0} onClick={() => act(api.cancelAll, "Queue cleared")}>Cancel queue</button>
        </div>
        {p?.state !== "paper_out"
          ? <button class="btn" disabled={busy} onClick={() => act(() => api.paperOut(true), "Marked as out of paper")}>Paper ran out</button>
          : null}
        <button class="btn" disabled={busy} onClick={() => act(api.newRoll, "Paper counter reset")}>I loaded a new roll</button>
      </div>
    </Sheet>
  );
}

export function QueueCard({ job }: { job: Job }) {
  const pct = jobProgress(job.id);
  const active = job.state === "printing";
  return (
    <div class={`glass qcard ${active ? "tg" : ""}`}>
      <div class="grow stack" style="gap:6px">
        <div class="row" style="justify-content:space-between">
          <span class="h3" style="font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{job.title}</span>
          {active && <span class="num" style="font-size:13px;font-weight:700;color:var(--green)">Printing {pct}%</span>}
        </div>
        {active && <div class="bar"><i style={{ width: `${pct}%` }} /></div>}
        <span class="cap" style="font-size:12px">{active ? job.source : job.state === "held" ? "Held for quiet hours" : "Next in line"} · {job.source}</span>
      </div>
      <button class="btn" style="min-height:44px;padding:0 12px;font-size:14px" aria-label={`Cancel ${job.title}`}
        onClick={() => api.cancel(job.id).then(() => toast("Cancelled"))}><IconX width={18} />Cancel</button>
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
    if (!doc.blocks.length) { setPv(null); setError(null); return; }
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

/** The 1-bit "As printed" receipt from the same renderer the printer uses. */
export function AsPrinted(props: { doc: Doc; caption?: boolean }) {
  const { pv, loading, error } = usePreview(props.doc);
  return (
    <section aria-label="As printed" style="width:100%;display:flex;flex-direction:column;align-items:center">
      {props.caption !== false && <div class="dotscap">384 DOTS · 48 MM · 1-BIT</div>}
      <div class="rwrap" style="max-width:384px">
        <div class={`receipt bits img ${loading ? "loading" : ""}`}>
          {pv ? <img src={pv.url} alt="Preview of the printed slip" /> : <div class="shim" style="height:120px;margin:0 10px" />}
        </div>
      </div>
      {pv && <div class="cap" style="margin-top:8px">{Math.max(1, Math.round(pv.lengthMm / 10))} cm of paper</div>}
      {error && <div style="width:100%;margin-top:8px"><Banner>{error}</Banner></div>}
      {pv?.warnings.map((w) => <div style="width:100%;margin-top:8px"><Banner kind="warn">{w}</Banner></div>)}
    </section>
  );
}

// ---------------------------------------------------------- print moment --
// A print in flight: Create's canvas plays the slot + paper feed for it; everywhere the
// toast says "Printed" (or where it is in the queue) and the History badge counts up.
interface Moment { job: Job; img: string | null; t0: number }
export const moment = signal<Moment | null>(null);
export const historyBadge = signal(0);

function ordinal(n: number) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function startMoment(job: Job, img: string | null) {
  trackJob(job);
  moment.value = { job, img, t0: performance.now() };
  const st = printer.value?.state;
  const ahead = pendingJobs.value.filter((j) => j.id < job.id).length;
  if (st === "offline" || st === "paper_out") toast(`Added to the queue · ${ordinal(ahead + 1)}`);
  else if (ahead > 0) toast(`Added to the queue · ${ordinal(ahead + 1)}`);
}

export async function printWithMoment(doc: Doc, title?: string, copies = 1, extraFeed = 0): Promise<Job | null> {
  let img: string | null = null;
  try {
    img = (await fetchPreview(doc)).url;
  } catch { /* the print call reports errors */ }
  try {
    const r = await api.print(doc, copies, title, extraFeed);
    startMoment(r.job, img);
    return r.job;
  } catch (e) {
    toast(e instanceof ApiError ? e.message : "Couldn't print. Try again.");
    return null;
  }
}

/** Global watcher: ends the moment, shows the toast, bumps the History badge. */
export function PrintMoment() {
  const m = moment.value;
  const job = m ? jobs.value.get(m.job.id) ?? m.job : null;
  useEffect(() => {
    if (!m || !job) return;
    if (job.state === "done") {
      const wait = Math.max(0, 1560 - (performance.now() - m.t0)); // let the feed finish first
      const t = window.setTimeout(() => {
        toast("Printed");
        historyBadge.value += 1;
        window.setTimeout(() => { if (moment.value?.job.id === job.id) moment.value = null; }, 650);
      }, wait);
      return () => window.clearTimeout(t);
    }
    if (job.state === "failed" || job.state === "cancelled") {
      toast(job.state === "cancelled" ? "Cancelled" : "Didn't print. It's in History.");
      moment.value = null;
    }
  }, [job?.state]);
  return null;
}

export function PrinterBanner() {
  const p = printer.value;
  if (p?.state === "offline") return <Banner kind="warn">Printer is offline. Check its USB cable and power. Prints wait in the queue.</Banner>;
  if (p?.state === "paper_out")
    return <Banner action={<button class="btn" onClick={() => api.newRoll().then(() => toast("New roll noted"))} style="color:var(--pink-text)">Retry</button>}>Paper ran out. Load a new roll, then tap Retry.</Banner>;
  return null;
}

export function CopiesSheet(props: { open: boolean; onClose: () => void; copies: number; feed: number; onChange: (c: number, f: number) => void; onPrint: () => void }) {
  return (
    <Sheet open={props.open} onClose={props.onClose} title="Print options">
      <div class="glass grp">
        <div class="lrow">Copies
          <div class="row" style="margin-left:auto;gap:6px">
            <button class="ib tile" aria-label="Fewer copies" onClick={() => props.onChange(Math.max(1, props.copies - 1), props.feed)}>−</button>
            <span class="num" style="width:40px;text-align:center" aria-live="polite">{props.copies}</span>
            <button class="ib tile" aria-label="More copies" onClick={() => props.onChange(Math.min(5, props.copies + 1), props.feed)}>+</button>
          </div>
        </div>
        <div class="lrow">Extra blank feed
          <div style="margin-left:auto">
            <Seg small label="Extra blank feed" width="190px" value={String(props.feed)} onChange={(v) => props.onChange(props.copies, Number(v))}
              options={["0", "2", "4", "8"].map((v) => ({ value: v, label: v === "0" ? "None" : `${v} lines` }))} />
          </div>
        </div>
      </div>
      <button class="btn-print block" style="width:100%;margin-top:14px" onClick={() => { props.onPrint(); props.onClose(); }}>Print {props.copies > 1 ? `${props.copies} copies` : "now"}</button>
    </Sheet>
  );
}
