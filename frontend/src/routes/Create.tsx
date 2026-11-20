import { useEffect, useMemo, useState } from "preact/hooks";
import { api, send, type Align, type Block, type Doc, type FontInfo, type Size } from "../lib/api";
import { settings } from "../lib/state";
import { IconCheck, IconDraw, IconImage, IconTemplate, IconText } from "../components/icons";
import { AsPrinted, PrinterBanner, printWithMoment, StatusPill } from "../components/printer";
import { Seg, toast, Toggle, Topbar } from "../components/ui";
import { DrawMode } from "./create/DrawMode";
import { ImageMode } from "./create/ImageMode";
import { TemplatesMode } from "./create/TemplatesMode";
import { QuickActions } from "./create/QuickActions";
import { ListMode } from "./create/ListMode";

export type Mode = "text" | "draw" | "image" | "templates" | "list";

interface TextDraft {
  heading: string;
  text: string;
  font: string;
  size: Size;
  align: Align;
  bold: boolean;
  invert: boolean;
  date: boolean;
  divider: boolean;
  border: boolean;
  qr: string;
}

const DRAFT_KEY = "wot.textDraft";
const blank = (): TextDraft => ({
  heading: "", text: "", font: settings.value?.printer?.default_font ?? "mono", size: settings.value?.printer?.default_size ?? "M",
  align: "left", bold: false, invert: false, date: false, divider: false, border: false, qr: "",
});

function loadDraft(): TextDraft {
  try {
    return { ...blank(), ...JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}") };
  } catch {
    return blank();
  }
}

export function textDoc(d: TextDraft): Doc {
  const blocks: Block[] = [];
  if (d.date) blocks.push({ type: "datetime", size: "S", align: "center" });
  if (d.heading.trim()) blocks.push({ type: "heading", text: d.heading.trim(), font: d.font, size: "XL", align: d.align === "left" ? "left" : d.align, invert: d.invert });
  if (d.divider && d.heading.trim()) blocks.push({ type: "divider", style: "dashed" });
  if (d.text) blocks.push({ type: "text", text: d.text, font: d.font, size: d.size, align: d.align, bold: d.bold, invert: d.invert && !d.heading.trim() });
  if (d.qr.trim()) blocks.push({ type: "qr", data: d.qr.trim(), size: "S", caption: d.qr.trim().length < 40 ? d.qr.trim() : undefined });
  return { blocks, options: { border: d.border } };
}

export function Create(props: { mode?: Mode }) {
  const [mode, setMode] = useState<Mode>(props.mode ?? "text");
  useEffect(() => { if (props.mode) setMode(props.mode); }, [props.mode]);
  return (
    <>
      <Topbar title="Create"><StatusPill /></Topbar>
      <PrinterBanner />
      <QuickActions />
      <div class="chips" role="tablist" aria-label="What to make" style="margin:10px 0 6px">
        {([["text", "Text", IconText], ["draw", "Draw", IconDraw], ["image", "Image", IconImage], ["templates", "Templates", IconTemplate], ["list", "List", IconCheck]] as const).map(([m, label, I]) => (
          <button class="chip" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}>
            <I width={16} height={16} />{label}
          </button>
        ))}
      </div>
      {mode === "text" && <TextMode />}
      {mode === "draw" && <DrawMode />}
      {mode === "image" && <ImageMode />}
      {mode === "templates" && <TemplatesMode onUse={() => setMode("text")} />}
      {mode === "list" && <ListMode />}
    </>
  );
}

export function useFonts() {
  const [fonts, setFonts] = useState<FontInfo[]>([]);
  useEffect(() => { api.fonts().then(setFonts).catch(() => {}); }, []);
  return fonts;
}

export function FontChips(props: { value: string; onChange: (v: string) => void }) {
  const fonts = useFonts();
  const css: Record<string, string> = { mono: "Space Mono", pixel: "VT323", silk: "Silkscreen", sans: "Inter" };
  return (
    <div class="chips" role="group" aria-label="Font">
      {fonts.map((f) => (
        <button class="chip" aria-pressed={props.value === f.id} onClick={() => props.onChange(f.id)}
          style={{ fontFamily: css[f.id] ? `"${css[f.id]}"` : undefined, fontSize: f.id === "pixel" ? "18px" : undefined }}>
          {f.name}
        </button>
      ))}
    </div>
  );
}

function TextMode() {
  const [d, setD] = useState<TextDraft>(loadDraft);
  const [copies, setCopies] = useState(1);
  const [more, setMore] = useState(false);
  const set = (p: Partial<TextDraft>) => setD((x) => ({ ...x, ...p }));
  useEffect(() => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch { /* private mode */ } }, [d]);
  const doc = useMemo(() => textDoc(d), [d]);
  const empty = doc.blocks.filter((b) => b.type !== "datetime").length === 0;
  const print = async () => {
    const j = await printWithMoment(doc, d.heading.trim() || undefined, copies);
    if (j) setD((x) => ({ ...x, text: "", heading: "", qr: "" }));
  };
  return (
    <div class="create-grid">
      <div>
        <label class="field-label" for="note">Your note</label>
        <textarea id="note" class="input" placeholder="Type something to print…" value={d.text} maxLength={4000}
          onInput={(e) => set({ text: (e.target as HTMLTextAreaElement).value })}
          style={{ fontFamily: { mono: "Space Mono", pixel: "VT323", silk: "Silkscreen", sans: "Inter" }[d.font] ?? "inherit", fontSize: d.font === "pixel" ? "20px" : undefined }} />
        <label class="field-label">Font</label>
        <FontChips value={d.font} onChange={(font) => set({ font })} />
        <div class="row wrap" style="margin-top:8px;gap:10px">
          <Seg label="Size" value={d.size} onChange={(size) => set({ size })} options={(["S", "M", "L", "XL"] as Size[]).map((s) => ({ value: s, label: s }))} />
          <Seg label="Align" value={d.align} onChange={(align) => set({ align })} options={[{ value: "left", label: "Left" }, { value: "center", label: "Centre" }, { value: "right", label: "Right" }]} />
        </div>
        <div class="glass list" style="margin-top:12px">
          <div class="lrow"><span class="grow">Bold</span><Toggle label="Bold" checked={d.bold} onChange={(bold) => set({ bold })} /></div>
          <div class="lrow"><span class="grow">White on black</span><Toggle label="White on black" checked={d.invert} onChange={(invert) => set({ invert })} /></div>
          <button class="lrow" onClick={() => setMore(!more)} aria-expanded={more}><span class="grow">More options</span><span class="meta">{more ? "Hide" : "Heading, date, QR, border"}</span></button>
          {more && (
            <>
              <div class="lrow" style="flex-direction:column;align-items:stretch">
                <label class="field-label" for="heading" style="margin-top:0">Heading</label>
                <input id="heading" class="input" value={d.heading} maxLength={80} placeholder="Optional big title" onInput={(e) => set({ heading: (e.target as HTMLInputElement).value })} />
              </div>
              <div class="lrow"><span class="grow">Date and time on top</span><Toggle label="Date and time on top" checked={d.date} onChange={(date) => set({ date })} /></div>
              <div class="lrow"><span class="grow">Line under the heading</span><Toggle label="Line under the heading" checked={d.divider} onChange={(divider) => set({ divider })} /></div>
              <div class="lrow"><span class="grow">Border</span><Toggle label="Border" checked={d.border} onChange={(border) => set({ border })} /></div>
              <div class="lrow" style="flex-direction:column;align-items:stretch">
                <label class="field-label" for="qr" style="margin-top:0">QR code (link or text)</label>
                <input id="qr" class="input" value={d.qr} maxLength={500} placeholder="https://…" onInput={(e) => set({ qr: (e.target as HTMLInputElement).value })} />
              </div>
            </>
          )}
        </div>
      </div>
      <div>
        <AsPrinted doc={doc} />
        <PrintBar disabled={empty} copies={copies} setCopies={setCopies} onPrint={print} onClear={() => setD(blank())} />
        {!empty && (
          <button class="btn btn-ghost block small" style="margin-top:8px" onClick={async () => {
            const name = window.prompt("Name this template", d.heading.trim() || d.text.trim().split("\n")[0].slice(0, 30));
            if (!name) return;
            try { await send("POST", "/api/templates", { name, document: doc }); toast("Saved to Templates"); } catch (e) { toast((e as Error).message); }
          }}>Save as template</button>
        )}
      </div>
    </div>
  );
}

export function PrintBar(props: { disabled: boolean; copies: number; setCopies: (n: number) => void; onPrint: () => void; onClear?: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div class="row" style="margin-top:18px;gap:10px">
      {props.onClear && <button class="btn btn-ghost" onClick={props.onClear}>Clear</button>}
      <div class="seg" role="group" aria-label="Copies">
        <button aria-label="Fewer copies" onClick={() => props.setCopies(Math.max(1, props.copies - 1))}>−</button>
        <span style="padding:7px 6px;font-weight:700;min-width:36px;text-align:center" aria-live="polite">×{props.copies}</span>
        <button aria-label="More copies" onClick={() => props.setCopies(Math.min(10, props.copies + 1))}>+</button>
      </div>
      <button class="btn btn-green btn-print" disabled={props.disabled || busy}
        onClick={async () => { setBusy(true); try { await props.onPrint(); } finally { setBusy(false); } }}>
        Print
      </button>
    </div>
  );
}
