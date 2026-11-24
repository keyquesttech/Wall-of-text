// Draw (HANDOFF 7.1): finger drawing in black on the paper strip. 1 canvas px = 1 printer dot.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Doc } from "../../lib/api";
import { IconEraser, IconLine, IconRedo, IconUndo } from "../../components/icons";
import { ActionRow, SideButtons, Split, Toolbar, type View } from "../Create";

const W = 384;
const HEIGHTS = [240, 384, 640];
type Tool = 3 | 6 | 14 | "erase" | "line";

export function DrawMode(props: { view: View; wide: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hi, setHi] = useState(1);
  const [tool, setTool] = useState<Tool>(6);
  const [pen, setPen] = useState(6);
  const [src, setSrc] = useState<string | null>(null);
  const undo = useRef<ImageData[]>([]);
  const redo = useRef<ImageData[]>([]);
  const [, bump] = useState(0);
  const drawing = useRef<{ x: number; y: number; start: { x: number; y: number }; snap: ImageData } | null>(null);
  const H = HEIGHTS[hi];

  const ctx = () => canvas.current!.getContext("2d")!;
  const snapshot = () => setSrc(canvas.current!.toDataURL("image/png"));
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const prev = src;
    c.width = W;
    c.height = H;
    const x = ctx();
    x.fillStyle = "#fff";
    x.fillRect(0, 0, W, H);
    if (prev) { const im = new Image(); im.onload = () => { x.drawImage(im, 0, 0); }; im.src = prev; }
  }, [H, props.view]);

  const pos = (e: PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * W) / r.width, y: ((e.clientY - r.top) * H) / r.height };
  };
  const stroke = (a: { x: number; y: number }, b: { x: number; y: number }) => {
    const c = ctx();
    c.strokeStyle = tool === "erase" ? "#fff" : "#000";
    c.lineWidth = tool === "erase" ? 24 : pen;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.beginPath();
    c.moveTo(a.x, a.y);
    c.lineTo(b.x + 0.01, b.y);
    c.stroke();
  };
  const down = (e: PointerEvent) => {
    e.preventDefault();
    canvas.current!.setPointerCapture(e.pointerId);
    const snap = ctx().getImageData(0, 0, W, H);
    undo.current.push(snap);
    if (undo.current.length > 30) undo.current.shift();
    redo.current = [];
    const p = pos(e);
    drawing.current = { ...p, start: p, snap };
    if (tool !== "line") stroke(p, p);
  };
  const move = (e: PointerEvent) => {
    const d = drawing.current;
    if (!d) return;
    const p = pos(e);
    if (tool === "line") { ctx().putImageData(d.snap, 0, 0); stroke(d.start, p); }
    else { stroke(d, p); d.x = p.x; d.y = p.y; }
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = null;
    snapshot();
    bump((n) => n + 1);
  };
  const doUndo = () => {
    const d = undo.current.pop();
    if (!d) return;
    redo.current.push(ctx().getImageData(0, 0, W, H));
    ctx().putImageData(d, 0, 0);
    snapshot(); bump((n) => n + 1);
  };
  const doRedo = () => {
    const d = redo.current.pop();
    if (!d) return;
    undo.current.push(ctx().getImageData(0, 0, W, H));
    ctx().putImageData(d, 0, 0);
    snapshot(); bump((n) => n + 1);
  };
  const clear = () => {
    const c = ctx();
    c.fillStyle = "#fff";
    c.fillRect(0, 0, W, H);
    undo.current = []; redo.current = [];
    setSrc(null);
  };
  const pick = (t: Tool) => { setTool(t); if (typeof t === "number") setPen(t); };

  const doc: Doc = useMemo(() => ({ blocks: src ? [{ type: "drawing" as const, src }] : [] }), [src]);
  const edit = (
    <div class="rwrap" style="width:100%">
      <div class="receipt" style="padding:10px 10px 22px">
        <canvas ref={canvas} class="draw" aria-label="Drawing area. Draw with your finger, mouse or pen."
          onPointerDown={down as any} onPointerMove={move as any} onPointerUp={up} onPointerCancel={up} />
      </div>
    </div>
  );
  return (
    <>
      <Split view={props.view} wide={props.wide} doc={doc} edit={edit}
        side={<SideButtons doc={doc} name="Drawing" onClear={clear} />} />
      <Toolbar label="Drawing tools">
        <div class="row" style="gap:2px;flex:1;justify-content:space-between">
          {([3, 6, 14] as const).map((w, i) => (
            <button class={`ib ${tool === w ? "on" : ""}`} aria-pressed={tool === w} aria-label={["Thin pen", "Medium pen", "Thick pen"][i]} onClick={() => pick(w)}>
              <span style={{ width: `${[6, 11, 17][i]}px`, height: `${[6, 11, 17][i]}px`, borderRadius: "50%", background: tool === w ? "#ECEEF2" : "#C9CDD4" }} />
            </button>
          ))}
          <button class={`ib ${tool === "erase" ? "on" : ""}`} aria-pressed={tool === "erase"} aria-label="Eraser" onClick={() => pick("erase")}><IconEraser class="i" /></button>
          <button class={`ib ${tool === "line" ? "on" : ""}`} aria-pressed={tool === "line"} aria-label="Straight line" onClick={() => pick("line")}><IconLine class="i" /></button>
          <button class="ib" aria-label="Undo" disabled={!undo.current.length} onClick={doUndo}><IconUndo class="i" /></button>
          <button class="ib" aria-label="Redo" disabled={!redo.current.length} onClick={doRedo}><IconRedo class="i" /></button>
          <button class="ib" aria-label={`Paper length: ${["short", "square", "long"][hi]}. Change`} style="font-size:13px" onClick={() => setHi((hi + 1) % 3)}>{["S", "M", "L"][hi]}</button>
        </div>
      </Toolbar>
      <ActionRow doc={doc} title="Drawing" disabled={!src} />
    </>
  );
}
