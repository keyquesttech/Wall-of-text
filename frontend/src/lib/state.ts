// Live app state. SSE (/api/events) pushes changes; if it drops, poll every 3 s.
// After SSE has failed and polls fail too, `reachable` goes false and the
// "Can't reach Wall Printer" screen shows (BUILD_PLAN override 3).
import { signal, computed } from "@preact/signals";
import { api, type Job, type PrinterStatus, type WifiStatus, type AuthStatus } from "./api";

export const printer = signal<PrinterStatus | null>(null);
export const wifi = signal<WifiStatus | null>(null);
export const auth = signal<AuthStatus | null>(null);
export const jobs = signal<Map<number, Job>>(new Map());
export const reachable = signal(true);
export const settings = signal<any>(null);
export const lastJobEvent = signal<Job | null>(null);
export const progress = signal<Record<number, number>>({});
export const inboxWaiting = signal(0);
let toastHook: ((m: string) => void) | null = null;
export function onServerToast(fn: (m: string) => void) {
  toastHook = fn;
}

export const pendingJobs = computed(() =>
  [...jobs.value.values()].filter((j) => j.state === "queued" || j.state === "printing" || j.state === "held").sort((a, b) => a.id - b.id),
);

function upsertJob(j: Job) {
  const m = new Map(jobs.value);
  m.set(j.id, j);
  // keep the map small: drop finished jobs older than the 50 most recent
  if (m.size > 80) {
    const ids = [...m.keys()].sort((a, b) => a - b);
    for (const id of ids.slice(0, m.size - 80)) {
      const x = m.get(id)!;
      if (!["queued", "printing", "held"].includes(x.state)) m.delete(id);
    }
  }
  jobs.value = m;
  lastJobEvent.value = j;
}

let es: EventSource | null = null;
let pollTimer: number | undefined;
let failures = 0;

async function poll() {
  try {
    const [q, w] = await Promise.all([api.queue(), api.wifi()]);
    printer.value = q.printer;
    for (const j of q.jobs) upsertJob(j);
    // jobs that left the pending list: refresh their final state
    for (const j of jobs.value.values()) {
      if (["queued", "printing", "held"].includes(j.state) && !q.jobs.find((x) => x.id === j.id)) {
        const h = await api.historyItem(j.id).catch(() => null);
        if (h) upsertJob(h);
      }
    }
    wifi.value = w;
    failures = 0;
    reachable.value = true;
  } catch {
    failures += 1;
    if (failures >= 2) reachable.value = false;
  }
}

function startPolling() {
  if (pollTimer) return;
  poll();
  pollTimer = window.setInterval(poll, 3000);
}

function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = undefined;
}

export function connect() {
  if (es) es.close();
  try {
    es = new EventSource("/api/events");
  } catch {
    startPolling();
    return;
  }
  es.onopen = () => {
    stopPolling();
    failures = 0;
    reachable.value = true;
    api.queue().then((q) => q.jobs.forEach(upsertJob)).catch(() => {});
  };
  es.onerror = () => {
    // EventSource retries by itself; meanwhile poll so the UI stays live.
    startPolling();
  };
  es.addEventListener("printer", (e) => (printer.value = JSON.parse((e as MessageEvent).data)));
  es.addEventListener("wifi", (e) => (wifi.value = JSON.parse((e as MessageEvent).data)));
  es.addEventListener("job", (e) => upsertJob(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("progress", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    progress.value = { ...progress.value, [d.id]: d.progress };
  });
  es.addEventListener("settings", (e) => (settings.value = JSON.parse((e as MessageEvent).data)));
  es.addEventListener("toast", (e) => toastHook?.(JSON.parse((e as MessageEvent).data).message));
  es.addEventListener("inbox", (e) => (inboxWaiting.value = JSON.parse((e as MessageEvent).data).waiting ?? 0));
}

export async function boot() {
  connect();
  const [a, s, p] = await Promise.all([api.auth(), api.settings(), api.printer()]).catch(() => [null, null, null]);
  if (a) auth.value = a;
  if (s) settings.value = s;
  if (p) printer.value = p;
}

export function jobProgress(id: number): number {
  const live = progress.value[id];
  const j = jobs.value.get(id);
  if (j && j.state === "done") return 100;
  return live ?? j?.progress ?? 0;
}

export function trackJob(j: Job) {
  upsertJob(j);
}
