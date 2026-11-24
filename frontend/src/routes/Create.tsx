// Create (HANDOFF 7.1, reference Main.dc.html): pill + Edit/As printed, quick chips, mode switcher,
// the glass canvas with the paper strip, the mode toolbar, and Print + Schedule.
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { api, send, type Align, type Block, type Doc, type FontInfo, type Size } from "../lib/api";
import { jobProgress, jobs, pendingJobs, printer, settings } from "../lib/state";
import {
  IconAlarm, IconBookmark, IconCheck, IconCheckbox, IconDivider, IconPrint2, IconPlus, IconQR, IconTrash,
} from "../components/icons";
import { AsPrinted, CopiesSheet, moment, PrinterBanner, printWithMoment, StatusPill } from "../components/printer";
import { Seg, Sheet, toast } from "../components/ui";
import { openWizard } from "./Schedules";
import { DrawMode } from "./create/DrawMode";
import { ImageMode } from "./create/ImageMode";
import { TemplatesMode } from "./create/TemplatesMode";
import { ListMode } from "./create/ListMode";
import { QuickActions } from "./create/QuickActions";

export type Mode = "text" | "draw" | "image" | "list" | "templates";
const MODES: Mode[] = ["text", "draw", "image", "list", "templates"];
export type View = "edit" | "printed";

export const FONT_CSS: Record<string, string> = { mono: "'Space Mono', monospace", pixel: "VT323, monospace", silk: "Silkscreen, monospace", sans: "Inter, sans-serif" };
const SIZE_PX: Record<Size, number> = { S: 18, M: 22, L: 30, XL: 40 };
// pixel fonts print at grid-friendly sizes (backend render/fonts.py PIXEL_SIZES); mirror that on the strip
const PIXEL_PX: Record<string, Record<Size, number>> = { pixel: { S: 24, M: 30, L: 40, XL: 48 }, silk: { S: 16, M: 24, L: 32, XL: 40 } };
const SIZES: Size[] = ["S", "M", "L", "XL"];

// ------------------------------------------------------------------ Text draft --
interface TextDraft {
  title: string; text: string; font: string; size: Size; align: Align;
  bold: boolean; underline: boolean; invert: boolean; date: boolean; qr: string;
}
const DRAFT_KEY = "wot.textDraft.v2";
const blank = (): TextDraft => ({
  title: "", text: "", font: settings.value?.printer?.default_font ?? "pixel", size: settings.value?.printer?.default_size ?? "M",
  align: "left", bold: false, underline: false, invert: false, date: false, qr: "",
});
function loadDraft(): TextDraft {
  try { return { ...blank(), ...JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}") }; } catch { return blank(); }
}

/** Lines starting "☐ " become checklist items, a line of "---" a divider, the rest text. */
export function textDoc(d: TextDraft): Doc {
  const blocks: Block[] = [];
  if (d.date) blocks.push({ type: "datetime", size: "S", align: "center", format: "%a %-d %b · %H:%M" });
  if (d.title.trim()) blocks.push({ type: "heading", text: d.title.trim(), font: d.font, size: "XL", align: "center", invert: d.invert });
  let para: string[] = [];
  let items: { text: string; done?: boolean }[] = [];
  const flushPara = () => {
    const t = para.join("\n").replace(/^\n+|\n+$/g, "");
    if (t) blocks.push({ type: "text", text: t, font: d.font, size: d.size, align: d.align, bold: d.bold, underline: d.underline, invert: d.invert && !d.title.trim() });
    para = [];
  };
  const flushItems = () => { if (items.length) blocks.push({ type: "checklist", items, size: d.size, font: d.font, align: d.align }); items = []; };
  for (const line of d.text.split("\n")) {
    const m = /^\s*(☐|☑|\[ \]|\[x\])\s?(.*)$/i.exec(line);
    if (/^\s*-{3,}\s*$/.test(line)) { flushPara(); flushItems(); blocks.push({ type: "divider", style: "dashed" }); }
    else if (m) { flushPara(); items.push({ text: m[2], done: m[1] === "☑" || m[1].toLowerCase() === "[x]" }); }
    else { flushItems(); para.push(line); }
  }
  flushPara(); flushItems();
  if (d.qr.trim()) blocks.push({ type: "qr", data: d.qr.trim(), size: "S", caption: d.qr.trim().length < 40 ? d.qr.trim() : undefined });
  return { blocks };
}

// ---------------------------------------------------------------- shared pieces --
export function Canvas(props: { children: ComponentChildren; side?: ComponentChildren; label?: string }) {
  const m = moment.value;
  const job = m ? jobs.value.get(m.job.id) ?? m.job : null;
  const feeding = !!(m && m.img && job && !["failed", "cancelled"].includes(job.state));
  // HANDOFF 9: paper feeds for 1.4 s, tears at 1.56 s, but never before the real print is done.
  const [fed, setFed] = useState(false);
  useEffect(() => {
    setFed(false);
    if (!m) return;
    const t = window.setTimeout(() => setFed(true), Math.max(0, 1560 - (performance.now() - m.t0)));
    return () => window.clearTimeout(t);
  }, [m?.job.id]);
  const tearing = feeding && fed && job!.state === "done";
  return (
    <section class={`glass canvas ${feeding ? "feedingnow" : ""}`} aria-label={props.label ?? "Paper strip"}>
      <div class="strip fade-b">{props.children}</div>
      {props.side && <div class="side">{props.side}</div>}
      {feeding && (
        <div class="feedlayer" aria-hidden="true">
          <div class="slot" />
          <div class={`feedpaper rwrap ${tearing ? "tearing" : "feeding"}`} key={m!.job.id}>
            <div class="receipt bits img" style="padding:6px 0 18px"><img src={m!.img!} alt="" /></div>
          </div>
        </div>
      )}
    </section>
  );
}

/** Bookmark (save this print as your own template) and Clear, beside the paper in every mode. */
export function SideButtons(props: { doc?: Doc; name?: string; onClear: () => void }) {
  const [open, setOpen] = useState(false);
  const [tname, setTname] = useState("");
  const empty = !props.doc || props.doc.blocks.length === 0;
  return (
    <>
      {props.doc && (
        <button class="ib" aria-label="Save as template" onClick={() => {
          if (empty) { toast("Make something first, then save it as a template."); return; }
          setTname(props.name ?? ""); setOpen(true);
        }}><IconBookmark class="i" /></button>
      )}
      <button class="ib" aria-label="Clear the strip" onClick={props.onClear}><IconTrash class="i" /></button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Save as template">
        <label class="field-label" for="tn">Name</label>
        <input id="tn" class="input" value={tname} maxLength={60} onInput={(e) => setTname((e.target as HTMLInputElement).value)} />
        <p class="cap" style="margin:10px 4px 0">Tip: write a word in double braces, like {"{{name}}"}, anywhere in your text. It becomes a box to fill in each time you use the template.</p>
        <button class="btn-green block" style="margin-top:14px" disabled={!tname.trim()} onClick={async () => {
          try { await send("POST", "/api/templates", { name: tname.trim(), document: props.doc }); toast("Saved to Templates"); setOpen(false); } catch (e) { toast((e as Error).message); }
        }}>Save</button>
      </Sheet>
    </>
  );
}

export function Toolbar(props: { children: ComponentChildren; label: string }) {
  return <div class="glass toolbar" role="toolbar" aria-label={props.label}>{props.children}</div>;
}

/** Print (green, progress inside, long-press for copies) + Schedule (pink). */
export function ActionRow(props: { doc: Doc; title?: string; disabled?: boolean; onPrinted?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState<number | null>(null);
  const [opts, setOpts] = useState(false);
  const [copies, setCopies] = useState(1);
  const [feed, setFeed] = useState(0);
  const [doneFlash, setDoneFlash] = useState(false);
  const press = useRef<number | undefined>();
  const longFired = useRef(false);
  const st = printer.value?.state;
  const queueOnly = st === "offline" || st === "paper_out";
  const job = mine != null ? jobs.value.get(mine) : null;
  const printing = job?.state === "printing";
  const pct = job ? jobProgress(job.id) : 0;
  const ahead = job && job.state === "queued" ? pendingJobs.value.filter((j) => j.id < job.id).length : 0;
  useEffect(() => {
    if (job?.state === "done") {
      setDoneFlash(true);
      const t = window.setTimeout(() => { setDoneFlash(false); setMine(null); }, 1000);
      return () => window.clearTimeout(t);
    }
    if (job && ["failed", "cancelled"].includes(job.state)) setMine(null);
  }, [job?.state]);
  const go = async (c = copies, f = feed) => {
    if (props.disabled || busy) return;
    setBusy(true);
    try {
      const j = await printWithMoment(props.doc, props.title, c, f);
      if (j) { setMine(j.id); props.onPrinted?.(); }
    } finally { setBusy(false); setCopies(1); setFeed(0); }
  };
  const down = () => { longFired.current = false; press.current = window.setTimeout(() => { longFired.current = true; setOpts(true); }, 550); };
  const up = () => window.clearTimeout(press.current);
  const label = doneFlash ? "Printed" : printing ? `Printing… ${pct}%` : busy ? "Sending…" : "Print";
  return (
    <div class="actrow">
      {queueOnly ? (
        <button class="btn" style="flex:1;height:64px;border-radius:22px;font-size:17px;font-weight:700" disabled={props.disabled} onClick={() => go()}>
          <IconPlus class="i" />Add to queue
        </button>
      ) : (
        <button class="btn-print" disabled={props.disabled} aria-label="Print now. Long-press for copies and extra feed"
          onPointerDown={down} onPointerUp={up} onPointerLeave={up} onContextMenu={(e) => e.preventDefault()}
          onClick={() => { if (!longFired.current) go(); }}>
          {printing && <span class="prog" style={{ width: `${pct}%` }} />}
          {busy ? <span class="spin" aria-hidden="true" /> : doneFlash ? <IconCheck class="i" style="position:relative;stroke-width:2.6" /> : <IconPrint2 class="i" style="position:relative" />}
          <span class="lbl-p" aria-live="polite">{label}</span>
          {ahead > 0 && <span class="badge" style="position:relative;background:#06210F;color:#39FF88">{ahead + 1}{["th", "st", "nd", "rd"][((ahead + 1) % 100 - 20) % 10] || ["th", "st", "nd", "rd"][(ahead + 1) % 100] || "th"}</span>}
        </button>
      )}
      <button class="btn-sched" disabled={props.disabled} onClick={() => openWizard(props.doc, props.title)}>
        <IconAlarm class="i" />Schedule
      </button>
      <CopiesSheet open={opts} onClose={() => setOpts(false)} copies={copies} feed={feed}
        onChange={(c, f) => { setCopies(c); setFeed(f); }} onPrint={() => go(copies, feed)} />
    </div>
  );
}

// ------------------------------------------------------------------------ page --
export function Create(props: { mode?: string }) {
  const [mode, setMode] = useState<Mode>((MODES.includes(props.mode as Mode) ? props.mode : "text") as Mode);
  const [view, setView] = useState<View>("edit");
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => { if (props.mode && MODES.includes(props.mode as Mode)) setMode(props.mode as Mode); }, [props.mode]);
  const st = printer.value?.state;
  return (
    <>
      <h1 class="sr-only">Create</h1>
      <div class="topbar">
        <StatusPill />
        {!wide && mode !== "templates" && mode !== "list" && (
          <Seg small label="Preview" width="170px" value={view} onChange={setView}
            options={[{ value: "edit", label: "Edit" }, { value: "printed", label: "As printed" }]} />
        )}
      </div>
      {(st === "offline" || st === "paper_out") && <PrinterBanner />}
      <QuickActions />
      <Seg tabs label="Create mode" value={mode} onChange={(m) => { setMode(m); setView("edit"); }}
        options={[{ value: "text", label: "Text" }, { value: "draw", label: "Draw" }, { value: "image", label: "Image" }, { value: "list", label: "List" }, { value: "templates", label: "Templates" }]} />
      {mode === "text" && <TextMode view={view} wide={wide} />}
      {mode === "draw" && <DrawMode view={view} wide={wide} />}
      {mode === "image" && <ImageMode view={view} wide={wide} />}
      {mode === "list" && <section class="glass card" aria-label="Shopping list"><h2 class="h3" style="margin:0 0 4px">Shopping list</h2><p class="cap" style="margin:0 0 10px">Shared by everyone on the Wi-Fi. Add things now, print it on the way out.</p><ListMode /></section>}
      {mode === "templates" && <TemplatesMode onNew={() => { setMode("text"); setView("edit"); toast("Write your print, then tap the bookmark beside the paper to save it as a template."); }} />}
    </>
  );
}

/** Edit canvas and As printed side by side on wide screens, switched on phones. */
export function Split(props: { view: View; wide: boolean; edit: ComponentChildren; doc: Doc; side?: ComponentChildren }) {
  if (props.wide) {
    return (
      <div class="create-split">
        <Canvas side={props.side}>{props.edit}</Canvas>
        <section class="glass canvas" aria-label="As printed"><div class="strip"><AsPrinted doc={props.doc} /></div></section>
      </div>
    );
  }
  return <Canvas side={props.view === "edit" ? props.side : undefined}>{props.view === "edit" ? props.edit : <AsPrinted doc={props.doc} />}</Canvas>;
}

// ---------------------------------------------------------------------- Text --
function TextMode(props: { view: View; wide: boolean }) {
  const [d, setD] = useState<TextDraft>(loadDraft);
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  const [sheet, setSheet] = useState<null | "font" | "qr">(null);
  const [qr, setQr] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  const paper = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.75);
  const set = (p: Partial<TextDraft>) => setD((x) => ({ ...x, ...p }));
  useEffect(() => { api.fonts().then(setFonts).catch(() => {}); }, []);
  useEffect(() => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch { /* private mode */ } }, [d]);
  useEffect(() => {
    if (!paper.current) return;
    const ro = new ResizeObserver(([e]) => setScale(Math.max(0.5, e.contentRect.width / 384)));
    ro.observe(paper.current);
    return () => ro.disconnect();
  }, [props.view]);
  useEffect(() => { // grow the textarea with its content
    const t = ta.current;
    if (t) { t.style.height = "auto"; t.style.height = `${Math.max(220 * scale, t.scrollHeight)}px`; }
  }, [d.text, d.size, d.font, scale, props.view]);
  const doc = useMemo(() => textDoc(d), [d]);
  const empty = !d.text.trim() && !d.title.trim() && !d.qr;

  const insertLinePrefix = (prefix: string) => {
    const t = ta.current;
    const pos = t ? t.selectionStart : d.text.length;
    const start = d.text.lastIndexOf("\n", pos - 1) + 1;
    const next = d.text.slice(0, start) + prefix + d.text.slice(start);
    set({ text: next });
    requestAnimationFrame(() => { t?.focus(); t?.setSelectionRange(pos + prefix.length, pos + prefix.length); });
  };
  const insertLine = (line: string) => {
    const t = ta.current;
    const pos = t ? t.selectionEnd : d.text.length;
    const before = d.text.slice(0, pos);
    const add = (before && !before.endsWith("\n") ? "\n" : "") + line + "\n";
    set({ text: before + add + d.text.slice(pos) });
    requestAnimationFrame(() => { t?.focus(); t?.setSelectionRange(pos + add.length, pos + add.length); });
  };
  const cur = fonts.find((f) => f.id === d.font);
  const textStyle = {
    fontFamily: FONT_CSS[d.font] ?? "inherit",
    fontSize: `${(PIXEL_PX[d.font]?.[d.size] ?? SIZE_PX[d.size]) * scale}px`,
    fontWeight: d.bold ? 700 : 400,
    textDecoration: d.underline ? "underline" : "none",
    textAlign: d.align,
    ...(d.invert && !d.title.trim() ? { background: "#000", color: "var(--paper)" } : {}),
  } as const;

  const edit = (
    <div class="rwrap" style="width:100%" ref={paper}>
      <div class="receipt" style="min-height:300px;font-family:inherit">
        {d.date && <div class="r-c" style={{ fontFamily: FONT_CSS.pixel, fontSize: `${18 * scale * 1.25}px` }}>{new Date().toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }).toUpperCase()} · {new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</div>}
        <label class="sr-only" for="ttl">Title</label>
        <input id="ttl" class="onpaper-head" value={d.title} maxLength={60} placeholder="TITLE"
          style={{ fontFamily: FONT_CSS[d.font], fontSize: `${40 * scale * (d.font === "pixel" ? 1.2 : 1)}px`, ...(d.invert ? { background: "#000", color: "var(--paper)" } : {}) }}
          onInput={(e) => set({ title: (e.target as HTMLInputElement).value })} />
        <label class="sr-only" for="note">Your note</label>
        <textarea id="note" ref={ta} class="onpaper" value={d.text} maxLength={4000} placeholder="Type something to print…"
          style={textStyle} onInput={(e) => set({ text: (e.target as HTMLTextAreaElement).value })} />
        {d.qr && <div class="r-c r-s" style="margin-top:6px">[QR] {d.qr.slice(0, 30)}</div>}
      </div>
    </div>
  );
  const side = (
    <SideButtons doc={empty ? { blocks: [] } : doc} name={d.title.trim() || d.text.trim().split("\n")[0].slice(0, 30)}
      onClear={() => setD({ ...blank(), font: d.font, size: d.size })} />
  );
  return (
    <>
      <Split view={props.view} wide={props.wide} edit={edit} doc={doc} side={side} />
      <Toolbar label="Text tools">
        <div class="chips">
          <button class="ib on" aria-label={`Print font: ${cur?.name ?? d.font}. Change`} style={{ fontFamily: FONT_CSS[d.font], fontSize: d.font === "pixel" ? "22px" : "15px" }} onClick={() => setSheet("font")}>Aa</button>
          <button class="ib" aria-label={`Size: ${d.size}. Change`} onClick={() => set({ size: SIZES[(SIZES.indexOf(d.size) + 1) % 4] })}>{d.size}</button>
          <button class={`ib ${d.bold ? "on" : ""}`} aria-pressed={d.bold} aria-label="Bold" style="font-weight:900" onClick={() => set({ bold: !d.bold })}>B</button>
          <button class={`ib ${d.underline ? "on" : ""}`} aria-pressed={d.underline} aria-label="Underline" style="text-decoration:underline" onClick={() => set({ underline: !d.underline })}>U</button>
          <button class={`ib ${d.invert ? "on" : ""}`} aria-pressed={d.invert} aria-label="White on black" onClick={() => set({ invert: !d.invert })}><span style="background:#C9CDD4;color:#121315;padding:0 5px;border-radius:4px;font-size:14px">A</span></button>
          <button class="ib" aria-label={`Align ${d.align}. Change`} onClick={() => set({ align: d.align === "left" ? "center" : d.align === "center" ? "right" : "left" })}>
            <svg class="i" viewBox="0 0 24 24" aria-hidden="true">{d.align === "left" ? <path d="M4 6h16M4 10h10M4 14h16M4 18h10" /> : d.align === "center" ? <path d="M4 6h16M7 10h10M4 14h16M7 18h10" /> : <path d="M4 6h16M10 10h10M4 14h16M10 18h10" />}</svg>
          </button>
          <button class="ib" aria-label="Checkbox line" onClick={() => insertLinePrefix("☐ ")}><IconCheckbox class="i" /></button>
          <button class={`ib ${d.date ? "on" : ""}`} aria-pressed={d.date} aria-label="Date and time stamp" onClick={() => set({ date: !d.date })}><IconAlarm class="i" /></button>
          <button class="ib" aria-label="Divider line" onClick={() => insertLine("---")}><IconDivider class="i" /></button>
          <button class={`ib ${d.qr ? "on" : ""}`} aria-label="QR code from a link" onClick={() => { setQr(d.qr); setSheet("qr"); }}><IconQR class="i" /></button>
        </div>
      </Toolbar>
      <ActionRow doc={doc} title={d.title.trim() || undefined} disabled={empty}
        onPrinted={() => setD((x) => ({ ...x, title: "", text: "", qr: "" }))} />

      <Sheet open={sheet === "font"} onClose={() => setSheet(null)} title="Print font">
        <div class="stack">
          {fonts.map((f) => (
            <button class={`glass ${f.id === d.font ? "selg" : ""}`} style="border-radius:18px;padding:10px;text-align:left" onClick={() => { set({ font: f.id }); setSheet(null); }}>
              <div class="rwrap"><div class="receipt" style={{ padding: "8px 12px 18px", fontFamily: FONT_CSS[f.id] ?? "inherit", fontSize: f.id === "pixel" ? "26px" : "18px" }}>The quick brown fox</div></div>
              <div class="row" style="margin-top:6px;justify-content:space-between"><span class="h3" style="font-size:15px">{f.name}</span><span class="cap">{f.builtin ? "Built-in" : "Uploaded"}{f.min_readable && f.min_readable !== "S" ? ` · clear from ${f.min_readable}` : ""}</span></div>
            </button>
          ))}
        </div>
      </Sheet>
      <Sheet open={sheet === "qr"} onClose={() => setSheet(null)} title="QR code">
        <label class="field-label" for="qrl">Link or text</label>
        <input id="qrl" class="input" value={qr} placeholder="https://…" maxLength={500} onInput={(e) => setQr((e.target as HTMLInputElement).value)} />
        <div class="row" style="margin-top:14px">
          {d.qr && <button class="btn grow" onClick={() => { set({ qr: "" }); setSheet(null); }}>Remove</button>}
          <button class="btn-green grow" disabled={!qr.trim()} onClick={() => { set({ qr: qr.trim() }); setSheet(null); }}>Add QR code</button>
        </div>
      </Sheet>
    </>
  );
}

