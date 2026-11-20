// Draw: a 384-dot-wide canvas (1 canvas pixel = 1 printer dot). Pointer events for
// mouse, touch and pen. The PNG goes to the renderer as a "drawing" block (sharp threshold).
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Doc } from "../../lib/api";
import { AsPrinted, printWithMoment } from "../../components/printer";
import { Seg } from "../../components/ui";
import { PrintBar } from "../Create";

const W = 384;
const HEIGHTS = { S: 240, M: 384, L: 640 } as const;
type H = keyof typeof HEIGHTS;

export function DrawMode() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [h, setH] = useState<H>("M");
  const [pen, setPen] = useState(6);
  const [erase, setErase] = useState(false);
  const [caption, setCaption] = useState("");
  const [src, setSrc] = useState<string | null>(null);
  const [copies, setCopies] = useState(1);
  const undo = useRef<ImageData[]>([]);
  const drawing = useRef<{ x: number; y: number } | null>(null);

  const ctx = () => canvas.current!.getContext("2d")!;
  const snapshot = () => setSrc(canvas.current!.toDataURL("image/png"));
  const clear = () => {
    const c = ctx();
    c.fillStyle = "#fff";
    c.fillRect(0, 0, W, HEIGHTS[h]);
    undo.current = [];
    setSrc(null);
  };
  useEffect(() => {
    // keep what's drawn when the height changes
    const c = canvas.current!;
    const old = src ? new Image() : null;
    c.width = W;
    c.height = HEIGHTS[h];
    const x = ctx();
    x.fillStyle = "#fff";
    x.fillRect(0, 0, W, HEIGHTS[h]);
    if (old && src) { old.onload = () => { x.drawImage(old, 0, 0); snapshot(); }; old.src = src; }
  }, [h]);

  const pos = (e: PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * W) / r.width, y: ((e.clientY - r.top) * HEIGHTS[h]) / r.height };
  };
  const down = (e: PointerEvent) => {
    e.preventDefault();
    canvas.current!.setPointerCapture(e.pointerId);
    undo.current.push(ctx().getImageData(0, 0, W, HEIGHTS[h]));
    if (undo.current.length > 30) undo.current.shift();
    drawing.current = pos(e);
    line(drawing.current, drawing.current);
  };
  const move = (e: PointerEvent) => {
    if (!drawing.current) return;
    const p = pos(e);
    line(drawing.current, p);
    drawing.current = p;
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = null;
    snapshot();
  };
  const line = (a: { x: number; y: number }, b: { x: number; y: number }) => {
    const c = ctx();
    c.strokeStyle = erase ? "#fff" : "#000";
    c.lineWidth = erase ? pen * 3 : pen;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.beginPath();
    c.moveTo(a.x, a.y);
    c.lineTo(b.x + 0.01, b.y);
    c.stroke();
  };
  const doUndo = () => {
    const d = undo.current.pop();
    if (d) { ctx().putImageData(d, 0, 0); snapshot(); }
  };

  const doc: Doc = useMemo(() => ({
    blocks: [
      ...(src ? [{ type: "drawing" as const, src }] : []),
      ...(caption.trim() ? [{ type: "text" as const, text: caption.trim(), align: "center" as const, size: "M" as const }] : []),
    ],
  }), [src, caption]);

  return (
    <div class="create-grid">
      <div>
        <div class="row wrap" style="margin:8px 0;gap:10px">
          <Seg label="Pen" value={erase ? "erase" : String(pen)} onChange={(v) => { if (v === "erase") setErase(true); else { setErase(false); setPen(Number(v)); } }}
            options={[{ value: "3", label: "Fine" }, { value: "6", label: "Pen" }, { value: "14", label: "Marker" }, { value: "erase", label: "Eraser" }]} />
          <Seg label="Paper length" value={h} onChange={setH} options={[{ value: "S", label: "Short" }, { value: "M", label: "Square" }, { value: "L", label: "Long" }]} />
        </div>
        <canvas ref={canvas} class="draw" aria-label="Drawing area. Draw with your finger, mouse or pen."
          onPointerDown={down as any} onPointerMove={move as any} onPointerUp={up} onPointerCancel={up} onPointerLeave={up} />
        <div class="row" style="margin-top:8px">
          <button class="btn small" onClick={doUndo} disabled={!undo.current.length}>Undo</button>
          <button class="btn small btn-ghost" onClick={clear}>Clear</button>
        </div>
        <label class="field-label" for="cap">Caption (optional)</label>
        <input id="cap" class="input" value={caption} maxLength={80} onInput={(e) => setCaption((e.target as HTMLInputElement).value)} />
      </div>
      <div>
        <AsPrinted doc={doc} />
        <PrintBar disabled={!src} copies={copies} setCopies={setCopies} onPrint={() => printWithMoment(doc, caption.trim() || "Drawing", copies)} />
      </div>
    </div>
  );
}
