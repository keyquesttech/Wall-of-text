// Image: take or pick a photo with <input type=file accept=image/* capture> (getUserMedia
// needs HTTPS; BUILD_PLAN override 4). Scaled down on the phone before upload.
import { useMemo, useState } from "preact/hooks";
import type { Doc } from "../../lib/api";
import { IconImage } from "../../components/icons";
import { AsPrinted, printWithMoment, usePreview } from "../../components/printer";
import { Banner, Seg, Toggle } from "../../components/ui";
import { PrintBar } from "../Create";

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

export function ImageMode() {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [style, setStyle] = useState<"photo" | "sharp" | "halftone">("photo");
  const [dither, setDither] = useState<"floyd" | "atkinson">("floyd");
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1.1);
  const [invert, setInvert] = useState(false);
  const [lighten, setLighten] = useState(false);
  const [rotate, setRotate] = useState(0);
  const [caption, setCaption] = useState("");
  const [copies, setCopies] = useState(1);

  const doc: Doc = useMemo(() => ({
    blocks: [
      ...(src ? [{ type: "image" as const, src, style, dither, brightness, contrast, invert, lighten, rotate }] : []),
      ...(caption.trim() ? [{ type: "text" as const, text: caption.trim(), align: "center" as const }] : []),
    ],
  }), [src, style, dither, brightness, contrast, invert, lighten, rotate, caption]);
  const { pv } = usePreview(doc, 400);
  const dense = (pv?.coverage ?? 0) > 0.5;

  const onFile = async (e: Event) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    setErr(null);
    try { setSrc(await shrink(f)); } catch (x) { setErr((x as Error).message); }
  };

  return (
    <div class="create-grid">
      <div>
        {err && <Banner>{err}</Banner>}
        <input id="pic" type="file" accept="image/*" capture="environment" class="sr-only" onChange={onFile} />
        <input id="pic2" type="file" accept="image/*" class="sr-only" onChange={onFile} />
        <div class="row" style="margin:8px 0">
          <label for="pic" class="btn grow"><IconImage width={18} />Take a photo</label>
          <label for="pic2" class="btn grow">Choose a picture</label>
        </div>
        {src && (
          <>
            <label class="field-label">Style</label>
            <Seg label="Style" value={style} onChange={setStyle} options={[{ value: "photo", label: "Photo" }, { value: "sharp", label: "Sharp" }, { value: "halftone", label: "Halftone" }]} />
            {style === "photo" && (
              <div style="margin-top:8px">
                <Seg label="Dither" value={dither} onChange={setDither} options={[{ value: "floyd", label: "Smooth" }, { value: "atkinson", label: "Crisp" }]} />
              </div>
            )}
            <label class="field-label" for="br">Brightness</label>
            <input id="br" type="range" min={0.5} max={1.8} step={0.05} value={brightness} onChange={(e) => setBrightness(Number((e.target as HTMLInputElement).value))} />
            <label class="field-label" for="ct">Contrast</label>
            <input id="ct" type="range" min={0.5} max={2} step={0.05} value={contrast} onChange={(e) => setContrast(Number((e.target as HTMLInputElement).value))} />
            <div class="glass list" style="margin-top:12px">
              <div class="lrow"><span class="grow">Lighten for paper</span><Toggle label="Lighten for paper" checked={lighten} onChange={setLighten} /></div>
              <div class="lrow"><span class="grow">Invert</span><Toggle label="Invert" checked={invert} onChange={setInvert} /></div>
              <button class="lrow" onClick={() => setRotate((rotate + 90) % 360)}><span class="grow">Rotate</span><span class="meta">{rotate}°</span></button>
            </div>
            {dense && !lighten && (
              <Banner kind="warn" action={<button class="btn small" onClick={() => setLighten(true)}>Lighten</button>}>
                This picture is very dark. Dark prints can stick or streak on thermal paper.
              </Banner>
            )}
            <label class="field-label" for="icap">Caption (optional)</label>
            <input id="icap" class="input" value={caption} maxLength={80} onInput={(e) => setCaption((e.target as HTMLInputElement).value)} />
          </>
        )}
        {!src && <div class="empty"><IconImage /><p>Take or choose a picture to print it in black and white.</p></div>}
      </div>
      <div>
        {src && <AsPrinted doc={doc} />}
        <PrintBar disabled={!src} copies={copies} setCopies={setCopies} onPrint={() => printWithMoment(doc, caption.trim() || "Picture", copies)} />
      </div>
    </div>
  );
}
