// Templates (HANDOFF 7.1): 2-column gallery of mini receipts; filter chips in the toolbar.
import { useEffect, useState } from "preact/hooks";
import { get, send, type Doc, type Job } from "../../lib/api";
import { IconTrash } from "../../components/icons";
import { AsPrinted, startMoment } from "../../components/printer";
import { Sheet, toast } from "../../components/ui";
import { Toolbar } from "../Create";
import { openWizard } from "../Schedules";

interface Field { key: string; label: string; multiline?: boolean; list?: boolean }
interface Template { id: string; name: string; builtin: boolean; fields: Field[]; document: Doc; defaults?: Record<string, string> }

const KIND: Record<string, "Lists" | "Notes" | "Cards"> = {
  "b-todo": "Lists", "b-recipe": "Lists", "b-chore": "Lists", "b-note": "Notes", "b-big": "Notes", "b-wifi": "Notes", "b-card": "Cards", "b-sticker": "Cards",
};
const FILTERS = ["All", "Lists", "Notes", "Cards", "Mine"] as const;

export function TemplatesMode() {
  const [items, setItems] = useState<Template[]>([]);
  const [open, setOpen] = useState<Template | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const load = () => get<{ items: Template[] }>("/api/templates").then((r) => setItems(r.items));
  useEffect(() => { load(); }, []);
  const shown = items.filter((t) => filter === "All" || (filter === "Mine" ? !t.builtin : KIND[t.id] === filter));
  return (
    <>
      <section class="glass canvas" aria-label="Templates">
        <div class="tgrid">
          {shown.map((t) => (
            <button class="tcard" onClick={() => setOpen(t)}>
              <div class="rwrap"><div class="receipt bits"><img src={`/api/templates/${t.id}/thumb`} alt="" loading="lazy" /></div></div>
              <span class="tname">{t.name}</span>
            </button>
          ))}
          {filter === "Mine" && shown.length === 0 && <p class="cap" style="grid-column:1/-1">Save any print as a template with the bookmark button next to the paper.</p>}
        </div>
      </section>
      <Toolbar label="Template filters">
        <div class="chips" style="gap:4px">
          {FILTERS.map((f) => (
            <button class={`chip ${filter === f ? "on" : ""}`} aria-pressed={filter === f} style={{ height: "44px", border: 0, color: filter === f ? undefined : "var(--muted-sm)" }} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </Toolbar>
      {open && <Filler t={open} onClose={() => setOpen(null)} onDeleted={() => { setOpen(null); load(); }} />}
    </>
  );
}

function Filler({ t, onClose, onDeleted }: { t: Template; onClose: () => void; onDeleted: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({ ...(t.defaults ?? {}) });
  const [doc, setDoc] = useState<Doc>(t.document);
  useEffect(() => {
    const h = window.setTimeout(() => send<{ document: Doc }>("POST", `/api/templates/${t.id}/fill`, { values }).then((r) => setDoc(r.document)), 250);
    return () => window.clearTimeout(h);
  }, [JSON.stringify(values)]);
  const print = async () => {
    const r = await send<{ job: Job }>("POST", `/api/templates/${t.id}/fill`, { values, print: true });
    startMoment(r.job, null);
    onClose();
  };
  return (
    <Sheet open onClose={onClose} title={t.name}>
      <div class="stack">
        {t.fields.map((f) => (
          <div>
            <label class="field-label" for={`f-${f.key}`}>{f.label}</label>
            {f.multiline
              ? <textarea id={`f-${f.key}`} class="input" style="min-height:90px" value={values[f.key] ?? ""} onInput={(e) => setValues({ ...values, [f.key]: (e.target as HTMLTextAreaElement).value })} />
              : <input id={`f-${f.key}`} class="input" value={values[f.key] ?? ""} onInput={(e) => setValues({ ...values, [f.key]: (e.target as HTMLInputElement).value })} />}
          </div>
        ))}
        <AsPrinted doc={doc} />
        <div class="actrow">
          <button class="btn-print" onClick={() => print().catch((e) => toast(e.message))}>Print</button>
          <button class="btn-sched" onClick={() => { onClose(); openWizard(doc, t.name); }}>Schedule</button>
        </div>
        {!t.builtin && <button class="btn btn-danger" onClick={() => send("DELETE", `/api/templates/${t.id}`).then(onDeleted)}><IconTrash class="i" />Delete template</button>}
      </div>
    </Sheet>
  );
}
