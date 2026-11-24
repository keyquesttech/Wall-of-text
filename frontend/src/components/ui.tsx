// Shared UI built on design-handoff/tokens.css components.
import { signal } from "@preact/signals";
import type { ComponentChildren } from "preact";
import { useEffect, useRef } from "preact/hooks";
import { IconAlert, IconCheck } from "./icons";

// ----------------------------------------------------------------- toast --
export const toastMsg = signal<string | null>(null);
let toastTimer: number | undefined;
export function toast(msg: string, ms = 1800) {
  toastMsg.value = msg;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toastMsg.value = null), ms);
}
export function Toast() {
  return toastMsg.value ? (
    <div class="glass toastf" role="status" aria-live="polite" key={toastMsg.value}>
      <IconCheck />{toastMsg.value}
    </div>
  ) : null;
}

// ----------------------------------------------------------------- sheet --
export function Sheet(props: { open: boolean; onClose: () => void; title?: string; label?: string; tint?: "tp" | "tg"; children: ComponentChildren }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!props.open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onClose();
      if (e.key === "Tab" && ref.current) {
        const f = ref.current.querySelectorAll<HTMLElement>("button:not([disabled]), [href], input, textarea, select, [tabindex]:not([tabindex='-1'])");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
        else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
      }
    };
    document.addEventListener("keydown", onKey);
    setTimeout(() => {
      // only if the user hasn't already moved focus into the sheet
      if (ref.current && !ref.current.contains(document.activeElement))
        ref.current.querySelector<HTMLElement>("input, textarea, button")?.focus();
    }, 30);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [props.open]);
  // Swipe down to close (from the pill, the title, or anywhere once the sheet is scrolled to the top).
  const drag = useRef<{ y0: number; t0: number; dy: number; on: boolean } | null>(null);
  const onTouchStart = (e: TouchEvent) => {
    const el = ref.current;
    const target = e.target as HTMLElement;
    if (!el || target.closest("textarea, input[type=range], canvas, .nodrag")) return;
    const fromTop = !!target.closest(".grabbtn, h2");
    if (!fromTop && el.scrollTop > 0) return;
    drag.current = { y0: e.touches[0].clientY, t0: performance.now(), dy: 0, on: false };
  };
  const onTouchMove = (e: TouchEvent) => {
    const d = drag.current, el = ref.current;
    if (!d || !el) return;
    d.dy = e.touches[0].clientY - d.y0;
    if (!d.on && d.dy > 8) { d.on = true; el.style.transition = "none"; }
    if (d.on) {
      if (e.cancelable) e.preventDefault();
      el.style.transform = `translateY(${Math.max(0, d.dy)}px)`;
    }
  };
  const onTouchEnd = () => {
    const d = drag.current, el = ref.current;
    drag.current = null;
    if (!d || !el || !d.on) return;
    const fast = d.dy / Math.max(1, performance.now() - d.t0) > 0.6;
    el.style.transition = "transform .22s ease-out";
    if (d.dy > 110 || (fast && d.dy > 40)) {
      el.style.transform = "translateY(100%)";
      window.setTimeout(props.onClose, 200);
    } else {
      el.style.transform = "";
    }
  };
  useEffect(() => { // touchmove must be non-passive to stop the page scrolling while dragging
    const el = ref.current;
    if (!props.open || !el) return;
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    return () => el.removeEventListener("touchmove", onTouchMove);
  }, [props.open]);
  if (!props.open) return null;
  return (
    <div class="scrimf" onClick={(e) => e.target === e.currentTarget && props.onClose()}>
      <section class={`glass sheetf ${props.tint ?? ""}`} role="dialog" aria-modal="true" aria-label={props.label ?? props.title} ref={ref}
        onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} onTouchCancel={onTouchEnd}>
        <button type="button" class="grabbtn" aria-label="Close" onClick={props.onClose}><span class="grab" /></button>
        {props.title && <h2 class="h2">{props.title}</h2>}
        {props.children}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- banner --
// Errors: pink + icon + plain sentence (HANDOFF 4). Info/warn use the neutral glass banner.
export function Banner(props: { kind?: "info" | "warn" | "error"; children: ComponentChildren; action?: ComponentChildren }) {
  const err = !props.kind || props.kind === "error";
  return (
    <div class={`glass banner ${err ? "pk" : props.kind === "info" ? "tg" : ""}`} role={props.kind === "info" ? "status" : "alert"}>
      <span class={`ico ${err ? "p" : props.kind === "info" ? "g" : "p"}`}>{props.kind === "info" ? <IconCheck /> : <IconAlert />}</span>
      <div class="btxt">{props.children}</div>
      {props.action}
    </div>
  );
}

// ---------------------------------------------------------------- toggle --
export function Toggle(props: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean; pink?: boolean }) {
  return (
    <button type="button" class={`tog ${props.pink ? "pk" : ""} ${props.checked ? "on" : ""}`} role="switch" aria-checked={props.checked}
      aria-label={props.label} disabled={props.disabled} onClick={() => props.onChange(!props.checked)} />
  );
}

export function ToggleRow(props: { label: string; sub?: string; checked: boolean; onChange: (v: boolean) => void; pink?: boolean; icon?: ComponentChildren }) {
  return (
    <div class="lrow">
      {props.icon}
      <div class="grow">
        <div>{props.label}</div>
        {props.sub && <div class="cap">{props.sub}</div>}
      </div>
      <Toggle checked={props.checked} onChange={props.onChange} label={props.label} pink={props.pink} />
    </div>
  );
}

// ------------------------------------------------------------- segmented --
export function Seg<T extends string>(props: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string; small?: boolean; width?: string; tabs?: boolean }) {
  const n = props.options.length;
  const i = Math.max(0, props.options.findIndex((o) => o.value === props.value));
  const pad = props.small ? 3 : 4;
  return (
    <div class={`glass seg ${props.small ? "sm" : ""}`} role={props.tabs ? "tablist" : "group"} aria-label={props.label}
      style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, width: props.width }}>
      <span class="hl" aria-hidden="true" style={{ left: `calc(${pad}px + (100% - ${pad * 2}px) / ${n} * ${i})`, width: `calc((100% - ${pad * 2}px) / ${n})` }} />
      {props.options.map((o) => (
        <button type="button" class={props.value === o.value ? "act" : ""}
          {...(props.tabs ? { role: "tab", "aria-selected": props.value === o.value } : { "aria-pressed": props.value === o.value })}
          onClick={() => props.onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

// ----------------------------------------------------------------- header --
// Pill top-left (and an optional action top-right), then the page title (HANDOFF 5, 7).
export function Topbar(props: { title: string; children?: ComponentChildren; right?: ComponentChildren; back?: () => void; backLabel?: string }) {
  return (
    <>
      <header class="topbar">
        {props.back ? (
          <button class="glass btn backbtn" onClick={props.back} aria-label={`Back to ${props.backLabel ?? "Settings"}`}>
            <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>{props.backLabel ?? "Settings"}
          </button>
        ) : props.children}
        {props.back ? props.children : props.right}
      </header>
      <h1 class="h1 page-title" style={props.back ? "font-size:30px" : undefined}>{props.title}</h1>
    </>
  );
}

export function Group(props: { children: ComponentChildren; label?: string }) {
  return (
    <>
      {props.label && <span class="sect">{props.label}</span>}
      <div class="glass grp">{props.children}</div>
    </>
  );
}

export function Chevron() {
  return <span class="chevr" aria-hidden="true">›</span>;
}

export function timeAgo(ts: number): string {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  const d = new Date(ts * 1000);
  const today = new Date();
  const hm = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return hm;
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
