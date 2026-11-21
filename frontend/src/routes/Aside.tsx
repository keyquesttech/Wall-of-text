// Third column on wide screens (>= 1200 px): printer, queue, waiting for OK, recent prints.
import { useEffect, useState } from "preact/hooks";
import { api, type Job } from "../lib/api";
import { inboxWaiting, jobProgress, lastJobEvent, pendingJobs, printer } from "../lib/state";
import { StatusPill } from "../components/printer";
import { timeAgo } from "../components/ui";

export function Aside() {
  const [recent, setRecent] = useState<Job[]>([]);
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 1200px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1200px)");
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => {
    if (wide) api.history(undefined).then((r) => setRecent(r.items.filter((j) => j.state === "done").slice(0, 6))).catch(() => {});
  }, [wide, lastJobEvent.value?.state]);
  if (!wide) return null;
  return (
    <aside class="aside" aria-label="Printer and queue">
      <StatusPill />
      <p class="dim small" style="margin:10px 6px 0">Paper: about {printer.value?.paper_percent ?? 100}% left</p>
      <h2 class="section">Queue</h2>
      <div class="glass grp">
        {pendingJobs.value.length === 0 && <div class="lrow dim">Nothing waiting.</div>}
        {pendingJobs.value.map((j) => (
          <div class="lrow">
            <div class="grow">
              <div class="title">{j.title}</div>
              {j.state === "printing" && <div class="progress" style="margin-top:6px"><i style={{ width: `${jobProgress(j.id)}%` }} /></div>}
            </div>
            <span class="meta">{j.state === "printing" ? `${jobProgress(j.id)}%` : j.state === "held" ? "Held" : "Waiting"}</span>
          </div>
        ))}
      </div>
      {inboxWaiting.value > 0 && (
        <>
          <h2 class="section">Waiting for your OK</h2>
          <div class="glass grp"><a class="lrow" href="/settings/access"><span class="grow">{inboxWaiting.value} message{inboxWaiting.value === 1 ? "" : "s"}</span><span class="meta">Review</span></a></div>
        </>
      )}
      <h2 class="section">Recently printed</h2>
      <div class="glass grp">
        {recent.length === 0 && <div class="lrow dim">Nothing yet.</div>}
        {recent.map((j) => (
          <a class="lrow" href={`/history/${j.id}`}>
            <img class="thumb" src={`/api/history/${j.id}/image`} alt="" loading="lazy" />
            <div class="grow"><div class="title">{j.title}</div><div class="sub">{j.source} · {timeAgo(j.created_at)}</div></div>
          </a>
        ))}
      </div>
    </aside>
  );
}
