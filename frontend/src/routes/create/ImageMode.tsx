// Image (HANDOFF 7.1): take or pick a photo (<input type=file capture>, override 4); the converted
// 1-bit result shows live on the paper, with brightness and contrast under it.
import { useMemo, useState } from "preact/hooks";
import type { Doc } from "../../lib/api";
import { IconCamera, IconImage } from "../../components/icons";
import { usePreview } from "../../components/printer";
import { Banner } from "../../components/ui";
import { ActionRow, SideButtons, Split, Toolbar, type View } from "../Create";

async function shrink(file: File, max = 1100): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = () => rej(new Error("That file isn't a picture this browser can open."));
      i.src = url;
    });
    const s = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * s);
    c.height = Math.round(img.naturalHeight * s);
    const x = c.getContext("2d")!;
    x.fillStyle = "#fff";
    x.fillRect(0, 0, c.width, c.height);
    x.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.88);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function ImageMode(props: { view: View; wide: boolean }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [style, setStyle] = useState<"photo" | "sharp" | "halftone">("photo");
  const [dither, setDither] = useState<"floyd" | "atkinson">("floyd");
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1.1);
  const [invert, setInvert] = useState(false);
  const [lighten, setLighten] = useState(false);
  const [rotate, setRotate] = useState(0);

  const imgDoc: Doc = useMemo(() => ({
    blocks: src ? [{ type: "image" as const, src, style, dither, brightness, contrast, invert, lighten, rotate }] : [],
  }), [src, style, dither, brightness, contrast, invert, lighten, rotate]);
  const doc = imgDoc;
  const { pv, loading } = usePreview(imgDoc, 350);
  const dense = (pv?.coverage ?? 0) > 0.5;

  const onFile = async (e: Event) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    setErr(null);
    try { setSrc(await shrink(f)); } catch (x) { setErr((x as Error).message); }
    (e.target as HTMLInputElement).value = "";
  };

  const edit = (
    <div class="rwrap" style="width:100%">
      <div class="receipt" style="padding:12px 12px 24px;font-family:Inter,sans-serif">
        {!src && (
          <div class="col center" style="display:flex;flex-direction:column;align-items:center;gap:12px;padding:30px 0;color:#3A3C40">
            <IconImage width={40} height={40} />
            <span style="font-size:15px">Take or choose a photo.<br />It prints in black dots.</span>
            <label for="pic2" class="btn" style="color:var(--hi)">Choose a picture</label>
          </div>
        )}
        {src && (
          <>
            {pv ? <img src={pv.url} alt="Your photo as it will print" style={{ display: "block", width: "100%", imageRendering: "pixelated", opacity: loading ? 0.6 : 1 }} />
              : <div class="shim" style="height:200px" />}
            <div class="r-s r-c" style="margin-top:8px;font-family:VT323,monospace">{style === "photo" ? "PHOTO DITHER" : style === "sharp" ? "SHARP" : "HALFTONE"} · 384 DOTS</div>
            <div style="display:flex;flex-direction:column;gap:2px;margin-top:10px;font-size:12px;color:#3A3C40">
              <label for="br" style="font-weight:600">Brightness</label>
              <input id="br" type="range" min={0.5} max={1.8} step={0.05} value={brightness} style="accent-color:#121315" onChange={(e) => setBrightness(Number((e.target as HTMLInputElement).value))} />
              <label for="ct" style="font-weight:600">Contrast</label>
              <input id="ct" type="range" min={0.5} max={2} step={0.05} value={contrast} style="accent-color:#121315" onChange={(e) => setContrast(Number((e.target as HTMLInputElement).value))} />
            </div>
          </>
        )}
      </div>
    </div>
  );
  return (
    <>
      {err && <Banner>{err}</Banner>}
      {dense && !lighten && src && (
        <Banner kind="warn" action={<button class="btn" onClick={() => setLighten(true)}>Lighten</button>}>
          This picture is very dark. Dark prints can stick or streak on thermal paper.
        </Banner>
      )}
      <input id="pic" type="file" accept="image/*" capture="environment" class="sr-only" onChange={onFile} />
      <input id="pic2" type="file" accept="image/*" class="sr-only" onChange={onFile} />
      <Split view={props.view} wide={props.wide} doc={doc} edit={edit}
        side={<SideButtons doc={src ? doc : { blocks: [] }} name="Picture" onClear={() => setSrc(null)} />} />
      <Toolbar label="Picture tools">
        <div class="chips" style="gap:4px">
          <label for="pic" class="ib" aria-label="Take a photo"><IconCamera class="i" /></label>
          {([["photo", "Photo dither"], ["sharp", "Sharp"], ["halftone", "Halftone"]] as const).map(([v, l]) => (
            <button class={`chip ${style === v ? "on" : ""}`} aria-pressed={style === v} style={{ height: "44px", padding: "0 12px", fontSize: "13px", color: style === v ? undefined : "var(--muted-sm)", border: 0 }} onClick={() => setStyle(v)}>{l}</button>
          ))}
          {style === "photo" && <button class={`chip ${dither === "atkinson" ? "on" : ""}`} aria-pressed={dither === "atkinson"} style="height:44px;padding:0 12px;font-size:13px;border:0" onClick={() => setDither(dither === "floyd" ? "atkinson" : "floyd")}>Crisp</button>}
          <button class={`chip ${lighten ? "on" : ""}`} aria-pressed={lighten} style="height:44px;padding:0 12px;font-size:13px;border:0" onClick={() => setLighten(!lighten)}>Lighten</button>
          <button class={`chip ${invert ? "on" : ""}`} aria-pressed={invert} style="height:44px;padding:0 12px;font-size:13px;border:0" onClick={() => setInvert(!invert)}>Invert</button>
          <button class="chip" style="height:44px;padding:0 12px;font-size:13px;border:0" onClick={() => setRotate((rotate + 90) % 360)}>Rotate {rotate}°</button>
        </div>
      </Toolbar>
      <ActionRow doc={doc} title="Picture" disabled={!src} />
    </>
  );
}
