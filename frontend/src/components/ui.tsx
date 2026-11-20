import { signal } from "@preact/signals";
import type { ComponentChildren } from "preact";
import { useEffect, useRef } from "preact/hooks";
import { IconAlert, IconCheck } from "./icons";

// ----------------------------------------------------------------- toast --
export const toastMsg = signal<string | null>(null);
let toastTimer: number | undefined;
export function toast(msg: string, ms = 2600) {
  toastMsg.value = msg;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toastMsg.value = null), ms);
}
export function Toast() {
  return toastMsg.value ? (
    <div class="toast" role="status" aria-live="polite">
      {toastMsg.value}
    </div>
  ) : null;
}

// ----------------------------------------------------------------- sheet --
export function Sheet(props: { open: boolean; onClose: () => void; title?: string; children: ComponentChildren; labelledBy?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!props.open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onClose();
      if (e.key === "Tab" && ref.current) {
        const f = ref.current.querySelectorAll<HTMLElement>("button, [href], input, textarea, select, [tabindex]:not([tabindex='-1'])");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      }
    };
    document.addEventListener("keydown", onKey);
    setTimeout(() => ref.current?.querySelector<HTMLElement>("input, textarea, button")?.focus(), 30);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [props.open]);
  if (!props.open) return null;
  return (
    <div class="backdrop" onClick={(e) => e.target === e.currentTarget && props.onClose()}>
      <div class="sheet" role="dialog" aria-modal="true" aria-label={props.title} ref={ref}>
        <div class="grab" />
        {props.title && <h2>{props.title}</h2>}
        {props.children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- banner --
export function Banner(props: { kind?: "info" | "warn" | "error"; children: ComponentChildren; action?: ComponentChildren }) {
  const cls = props.kind === "info" ? "banner info" : props.kind === "warn" ? "banner warn" : "banner";
  return (
    <div class={cls} role={props.kind === "info" ? "status" : "alert"}>
      {props.kind === "info" ? <IconCheck /> : <IconAlert />}
      <div class="grow">{props.children}</div>
      {props.action}
    </div>
  );
}

// ---------------------------------------------------------------- toggle --
export function Toggle(props: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <span class="toggle">
      <input type="checkbox" role="switch" aria-label={props.label} checked={props.checked} disabled={props.disabled}
        onChange={(e) => props.onChange((e.target as HTMLInputElement).checked)} />
      <span />
    </span>
  );
}

export function ToggleRow(props: { label: string; sub?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div class="lrow">
      <div class="grow">
        <div class="title">{props.label}</div>
        {props.sub && <div class="sub" style="white-space:normal">{props.sub}</div>}
      </div>
      <Toggle checked={props.checked} onChange={props.onChange} label={props.label} />
    </div>
  );
}

export function Seg<T extends string>(props: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div class="seg" role="group" aria-label={props.label}>
      {props.options.map((o) => (
        <button type="button" aria-pressed={props.value === o.value} onClick={() => props.onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function Topbar(props: { title: string; children?: ComponentChildren; back?: () => void }) {
  return (
    <header class="topbar">
      {props.back && (
        <button class="icon-btn" onClick={props.back} aria-label="Back">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
        </button>
      )}
      <h1>{props.title}</h1>
      {props.children}
    </header>
  );
}

export function timeAgo(ts: number): string {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  const d = new Date(ts * 1000);
  const today = new Date();
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `Today ${hm}`;
  const y = new Date(today.getTime() - 86400000);
  if (d.toDateString() === y.toDateString()) return `Yesterday ${hm}`;
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + " " + hm;
}

export function useDebounced<T>(value: T, ms: number, fn: (v: T) => void) {
  useEffect(() => {
    const t = window.setTimeout(() => fn(value), ms);
    return () => window.clearTimeout(t);
  }, [value]);
}
