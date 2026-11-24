// Typed client for the Wall of Text backend. Every mutating call sends JSON
// (the backend rejects other content types as a cross-site guard).

export type Size = "S" | "M" | "L" | "XL";
export type Align = "left" | "center" | "right";

export type Block =
  | { type: "text"; text: string; size?: Size; font?: string; align?: Align; bold?: boolean; invert?: boolean; underline?: boolean }
  | { type: "heading"; text: string; size?: Size; font?: string; align?: Align; invert?: boolean }
  | { type: "banner"; text: string; size?: Size; font?: string }
  | { type: "divider"; style?: "solid" | "dashed" | "dotted" | "wave" | "double" | "stars" }
  | { type: "spacer"; height: number }
  | { type: "qr"; data: string; size?: "S" | "M" | "L"; caption?: string }
  | { type: "checklist"; items: { text: string; done?: boolean }[]; size?: Size; font?: string; align?: Align }
  | { type: "datetime"; format?: string; size?: Size; align?: Align }
  | { type: "image"; src: string; style?: "photo" | "sharp" | "halftone"; dither?: "floyd" | "atkinson" | "ordered"; brightness?: number; contrast?: number; invert?: boolean; lighten?: boolean; rotate?: number }
  | { type: "drawing"; src: string }
  | { type: "columns"; left: string; right: string; size?: Size; font?: string }
  | { type: "sticker"; name: string; size?: "S" | "M" | "L"; align?: Align };

export interface Doc {
  blocks: Block[];
  options?: { border?: boolean; gap?: number };
}

export type JobState = "held" | "queued" | "printing" | "done" | "failed" | "cancelled" | "missed";
export interface Job {
  id: number;
  source: string;
  title: string;
  state: JobState;
  error: string | null;
  created_at: number;
  finished_at: number | null;
  started_at: number | null;
  progress: number;
  copies: number;
  rows: number | null;
  held_until: number | null;
  meta: Record<string, unknown>;
  has_image: boolean;
}

export type PrinterState = "ready" | "printing" | "offline" | "paper_out";
export interface PrinterStatus {
  state: PrinterState;
  detail: string | null;
  paper_percent: number;
  queue_length: number;
  held: number;
  active: { id: number; progress: number } | null;
}

export interface WifiStatus {
  mode: "setup_ap" | "connecting" | "online" | "fallback_ap";
  ssid: string | null;
  ip: string | null;
  hostname: string;
  signal: number | null;
  last_error: string | null;
  last_error_text: string | null;
  pending_ssid: string | null;
  ap: { ssid: string; address: string; clients: number };
}

export interface AuthStatus {
  signed_in: boolean;
  ask_for_password: boolean;
  default_password_in_use: boolean;
  default_setup_wifi_password_in_use: boolean;
  password_file_warning?: string;
}

export interface FontInfo {
  id: string;
  name: string;
  builtin: boolean;
  has_bold: boolean;
  min_readable: string | null;
  url: string | null;
}

export interface Preview {
  url: string; // object URL of the PNG
  rows: number;
  lengthMm: number;
  coverage: number;
  warnings: string[];
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (r.status === 401) {
    // Session ended (password changed or signed out elsewhere).
    location.href = "/signin?next=" + encodeURIComponent(location.pathname);
    throw new ApiError(401, "sign_in_required", "Please sign in again.");
  }
  const text = await r.text();
  let data: any = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!r.ok) {
    const msg = data.message || (typeof data.detail === "string" ? data.detail : null) || "Something went wrong. Try again.";
    throw new ApiError(r.status, data.error || "error", msg);
  }
  return data as T;
}

export function get<T>(path: string): Promise<T> {
  return fetch(path, { credentials: "same-origin" }).then((r) => handle<T>(r));
}

export function send<T>(method: "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  return fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then((r) => handle<T>(r));
}

export function upload<T>(path: string, form: FormData): Promise<T> {
  return fetch(path, { method: "POST", credentials: "same-origin", body: form }).then((r) => handle<T>(r));
}

export async function preview(doc: Doc, signal?: AbortSignal): Promise<Preview> {
  const r = await fetch("/api/preview", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document: doc }),
    signal,
  });
  if (!r.ok) await handle(r);
  const blob = await r.blob();
  const warn = r.headers.get("X-Wot-Warnings") || "";
  return {
    url: URL.createObjectURL(blob),
    rows: Number(r.headers.get("X-Wot-Rows") || 0),
    lengthMm: Number(r.headers.get("X-Wot-Length-Mm") || 0),
    coverage: Number(r.headers.get("X-Wot-Coverage") || 0),
    warnings: warn ? warn.split(" | ") : [],
  };
}

export const api = {
  print: (document: Doc, copies = 1, title?: string, extra_feed = 0) =>
    send<{ job: Job; warnings: string[]; printer: PrinterStatus }>("POST", "/api/print", { document, copies, title, extra_feed }),
  queue: () => get<{ jobs: Job[]; printer: PrinterStatus }>("/api/queue"),
  cancel: (id: number) => send("POST", `/api/queue/${id}/cancel`),
  cancelAll: () => send("POST", "/api/queue/cancel-all"),
  retry: (id: number) => send<{ job: Job }>("POST", `/api/jobs/${id}/retry`),
  reprint: (id: number) => send<{ job: Job }>("POST", `/api/history/${id}/reprint`),
  history: (source?: string, before?: number, q?: string) =>
    get<{ items: Job[] }>(`/api/history?limit=40${source ? `&source=${source}` : ""}${before ? `&before=${before}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  historyItem: (id: number) => get<Job & { document: Doc | null }>(`/api/history/${id}`),
  deleteHistory: (id: number) => send("DELETE", `/api/history/${id}`),
  clearHistory: () => send("DELETE", "/api/history"),
  printer: () => get<PrinterStatus>("/api/printer"),
  testPage: () => send("POST", "/api/printer/test-page"),
  newRoll: () => send<PrinterStatus>("POST", "/api/printer/new-roll"),
  paperOut: (out: boolean) => send<PrinterStatus>("POST", "/api/printer/paper-out", { out }),
  fonts: () => get<FontInfo[]>("/api/fonts"),
  wifi: () => get<WifiStatus>("/api/wifi/status"),
  auth: () => get<AuthStatus>("/api/auth/status"),
  device: () => get<any>("/api/device"),
  settings: () => get<any>("/api/settings"),
  patchSettings: (changes: any) => send<any>("PATCH", "/api/settings", changes),
};
