// Print previews are 1-bit bitmaps, 384 dots wide, straight from the printer's renderer.
// Browsers scale them badly: nearest-neighbour drops whole rows of dots ("NOV" → "NCV") and
// bilinear blurs them, and few screens show a whole number of pixels per dot (phones are often
// 2.6–2.75 pixels per point). So each preview is redrawn at exactly the size it is shown, in
// device pixels:
//   • bigger than the bitmap: blown up by a whole number with hard edges, then shrunk the last
//     few percent with averaging, so every dot stays a sharp black square;
//   • smaller (thumbnails): shrunk in halving steps with averaging, so thin strokes turn grey
//     instead of vanishing.
// Only the display copy changes; the dots are the printer's dots. Big previews also open full
// size on tap.

const SEL = ".receipt img, .paper img, .feedpaper img, img.thumb, img.print-img";
const ZOOM_SEL = ".receipt.img img";
const MAX_AREA = 16_000_000; // stay under mobile Safari's canvas limit

interface State { orig: string; source: HTMLImageElement | null; made: string | null; madeFor: number; busy: boolean }
const states = new WeakMap<HTMLImageElement, State>();

function loadSource(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => {
    const im = new Image();
    im.onload = () => ok(im);
    im.onerror = fail;
    im.src = src;
  });
}

function canvas(w: number, h: number) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

/** The bitmap redrawn at `tw` device pixels wide. */
function redraw(src: HTMLImageElement, tw: number): HTMLCanvasElement {
  const w = src.naturalWidth, h = src.naturalHeight;
  const th = Math.round((h * tw) / w);
  let cur: HTMLCanvasElement | HTMLImageElement = src;
  let cw = w, ch = h;
  if (tw > w) {
    let k = Math.ceil(tw / w); // whole-number blow-up with hard edges first
    while (k > 1 && w * k * h * k > MAX_AREA) k--;
    if (k > 1) {
      const up = canvas(w * k, h * k);
      const ux = up.getContext("2d")!;
      ux.imageSmoothingEnabled = false;
      ux.drawImage(src, 0, 0, w * k, h * k);
      cur = up; cw = w * k; ch = h * k;
    }
  }
  while (cw / 2 >= tw) { // shrink in halving steps: true averaging, no dropped dots
    const half = canvas(cw / 2, ch / 2);
    const hx = half.getContext("2d")!;
    hx.imageSmoothingEnabled = true;
    hx.imageSmoothingQuality = "high";
    hx.drawImage(cur, 0, 0, half.width, half.height);
    cur = half; cw = half.width; ch = half.height;
  }
  const out = canvas(tw, th);
  const ox = out.getContext("2d")!;
  ox.imageSmoothingEnabled = cw !== tw;
  ox.imageSmoothingQuality = "high";
  ox.drawImage(cur, 0, 0, tw, th);
  return out;
}

async function update(img: HTMLImageElement) {
  const st = states.get(img);
  if (!st || st.busy) return;
  const dpr = window.devicePixelRatio || 1;
  const tw = Math.round(img.getBoundingClientRect().width * dpr);
  if (tw < 8) return;
  if (st.madeFor && Math.abs(st.madeFor - tw) / tw < 0.01) return;
  st.busy = true;
  try {
    const src = st.source && st.source.src === st.orig ? st.source : (st.source = await loadSource(st.orig));
    if (!src.naturalWidth || img.src !== (st.made ?? st.orig)) return; // replaced meanwhile
    if (tw === src.naturalWidth) { // already 1:1
      if (st.made) { URL.revokeObjectURL(st.made); st.made = null; img.src = st.orig; }
      st.madeFor = tw;
      return;
    }
    const blob: Blob | null = await new Promise((ok) => redraw(src, tw).toBlob(ok, "image/png"));
    if (!blob || img.src !== (st.made ?? st.orig)) return;
    const url = URL.createObjectURL(blob);
    if (st.made) URL.revokeObjectURL(st.made);
    st.made = url;
    st.madeFor = tw;
    img.src = url;
  } catch {
    /* leave the original image as it is */
  } finally {
    st.busy = false;
  }
}

function onLoad(img: HTMLImageElement) {
  let st = states.get(img);
  if (st && img.src === st.made) return; // our own redraw finished loading
  if (!st) { st = { orig: img.src, source: null, made: null, madeFor: 0, busy: false }; states.set(img, st); }
  else if (img.src !== st.orig) { // a new preview: start over
    if (st.made) URL.revokeObjectURL(st.made);
    Object.assign(st, { orig: img.src, source: null, made: null, madeFor: 0 });
  }
  update(img);
}

const ro = new ResizeObserver((entries) => entries.forEach((e) => update(e.target as HTMLImageElement)));
const seen = new WeakSet<HTMLImageElement>();

function watch(img: HTMLImageElement) {
  if (seen.has(img)) return;
  seen.add(img);
  img.addEventListener("load", () => onLoad(img));
  ro.observe(img);
  if (img.complete && img.naturalWidth) onLoad(img);
  if (img.matches(ZOOM_SEL)) {
    img.tabIndex = 0;
    img.title = "Show full size";
    img.classList.add("zoomable");
  }
}

function scan(root: ParentNode) {
  root.querySelectorAll<HTMLImageElement>(SEL).forEach(watch);
}

let viewer: HTMLDivElement | null = null;
let opener: HTMLElement | null = null;
function closeZoom() {
  viewer?.remove();
  viewer = null;
  opener?.focus();
}
function openZoom(img: HTMLImageElement) {
  closeZoom();
  opener = img;
  viewer = document.createElement("div");
  viewer.className = "zoomview";
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-label", "Print preview, full size");
  const close = document.createElement("button");
  close.className = "btn zoomclose";
  close.textContent = "Close";
  close.addEventListener("click", closeZoom);
  const paper = document.createElement("div");
  paper.className = "zoompaper";
  const big = document.createElement("img");
  big.src = states.get(img)?.orig ?? img.src;
  big.alt = img.alt || "Print preview";
  big.className = "print-img";
  paper.appendChild(big);
  viewer.append(close, paper);
  viewer.addEventListener("click", (e) => { if (e.target === viewer) closeZoom(); });
  document.body.appendChild(viewer);
  watch(big);
  close.focus();
}

export function startCrispPreviews() {
  scan(document);
  new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "attributes" && m.target instanceof HTMLImageElement) continue; // load handles src changes
      m.addedNodes.forEach((n) => {
        if (n instanceof HTMLImageElement && n.matches(SEL)) watch(n);
        else if (n instanceof HTMLElement) scan(n);
      });
    }
  }).observe(document.body, { childList: true, subtree: true });
  let t = 0;
  window.addEventListener("resize", () => { clearTimeout(t); t = window.setTimeout(() => document.querySelectorAll<HTMLImageElement>(SEL).forEach((i) => update(i)), 150); });
  document.addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    if (t instanceof HTMLImageElement && t.matches(ZOOM_SEL)) openZoom(t);
  });
  document.addEventListener("keydown", (e) => {
    if (viewer && e.key === "Escape") { e.stopPropagation(); closeZoom(); return; }
    const t = e.target as HTMLElement;
    if ((e.key === "Enter" || e.key === " ") && t instanceof HTMLImageElement && t.matches(ZOOM_SEL)) { e.preventDefault(); openZoom(t); }
  }, true);
}
