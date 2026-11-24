// Print previews are 1-bit bitmaps, 384 dots wide, straight from the printer's renderer.
// Shown smaller than one screen pixel per dot with nearest-neighbour scaling, the browser drops
// whole rows and columns of dots ("NOV" turns into "NCV"). So each preview picks its scaling:
// crisp (pixelated) only when every dot lands on a whole number of screen pixels, smooth
// otherwise. Big previews also open full size (1 dot = 1 CSS px, crisp on 1x/2x/3x screens).
// The bitmap itself is never changed: what you zoom into is exactly what prints.

const SEL = ".receipt img, .paper img, .feedpaper img, img.thumb, img.print-img";
const ZOOM_SEL = ".receipt.img img";

function update(img: HTMLImageElement) {
  if (!img.naturalWidth) return;
  const shown = img.getBoundingClientRect().width * (window.devicePixelRatio || 1);
  if (!shown) return;
  const ratio = shown / img.naturalWidth;
  const whole = ratio >= 0.98 && Math.abs(ratio - Math.round(ratio)) < 0.06;
  img.classList.toggle("px", whole || ratio >= 3.5);
  img.classList.toggle("smooth", !(whole || ratio >= 3.5));
}

const ro = new ResizeObserver((entries) => entries.forEach((e) => update(e.target as HTMLImageElement)));
const seen = new WeakSet<HTMLImageElement>();

function watch(img: HTMLImageElement) {
  if (seen.has(img)) return;
  seen.add(img);
  img.addEventListener("load", () => update(img));
  ro.observe(img);
  update(img);
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
  big.src = img.src;
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
    for (const m of muts) m.addedNodes.forEach((n) => {
      if (n instanceof HTMLImageElement && n.matches(SEL)) watch(n);
      else if (n instanceof HTMLElement) scan(n);
    });
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", () => document.querySelectorAll<HTMLImageElement>(SEL).forEach(update));
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
