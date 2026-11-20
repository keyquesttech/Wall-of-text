// Third column on wide screens (>= 1200 px): queue and recent prints. Phase 8 refines it.
import { pendingJobs, printer } from "../lib/state";
import { StatusPill } from "../components/printer";

export function Aside() {
  return (
    <aside class="aside" aria-label="Printer and queue">
      <StatusPill />
      <h2 class="section">Queue</h2>
      <div class="glass list">
        {pendingJobs.value.length === 0 && <div class="lrow dim">Nothing waiting.</div>}
        {pendingJobs.value.map((j) => (
          <div class="lrow"><span class="grow title">{j.title}</span><span class="meta">{j.state === "printing" ? `${j.progress}%` : j.state}</span></div>
        ))}
      </div>
      <p class="dim small" style="margin:12px 6px">Paper: about {printer.value?.paper_percent ?? 100}% left</p>
    </aside>
  );
}
