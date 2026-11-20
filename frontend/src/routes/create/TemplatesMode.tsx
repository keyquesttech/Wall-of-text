import { useEffect, useState } from "preact/hooks";
import { get, send, type Doc, type Job } from "../../lib/api";
import { trackJob } from "../../lib/state";
import { IconTrash } from "../../components/icons";
import { AsPrinted, moment } from "../../components/printer";
import { Sheet, toast } from "../../components/ui";

interface Field { key: string; label: string; multiline?: boolean; list?: boolean }
interface Template { id: string; name: string; builtin: boolean; fields: Field[]; document: Doc; defaults?: Record<string, string> }

export function TemplatesMode(_props: { onUse: () => void }) {
  const [items, setItems] = useState<Template[]>([]);
  const [open, setOpen] = useState<Template | null>(null);
  const load = () => get<{ items: Template[] }>("/api/templates").then((r) => setItems(r.items));
  useEffect(() => { load(); }, []);
  const mine = items.filter((t) => !t.builtin);
  return (
    <>
      <div class="tgrid">
        {items.filter((t) => t.builtin).map((t) => (
          <button class="glass tcard" onClick={() => setOpen(t)}>
            <span class="tname">{t.name}</span>
            <span class="dim tiny">{t.fields.map((f) => f.label.split(" (")[0]).join(", ")}</span>
          </button>
        ))}
      </div>
      <h2 class="section">Saved by you</h2>
      <div class="glass list">
        {mine.length === 0 && <div class="lrow dim">Use "Save as template" on any print to keep it here.</div>}
        {mine.map((t) => (
          <div class="lrow">
            <button class="grow" style="background:none;border:0;text-align:left;padding:0" onClick={() => setOpen(t)}>{t.name}</button>
            <button class="icon-btn" aria-label={`Delete ${t.name}`} onClick={() => send("DELETE", `/api/templates/${t.id}`).then(load)}><IconTrash /></button>
          </div>
        ))}
      </div>
      {open && <Filler t={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function Filler({ t, onClose }: { t: Template; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({ ...(t.defaults ?? {}) });
  const [doc, setDoc] = useState<Doc>(t.document);
  useEffect(() => {
    const h = window.setTimeout(() => send<{ document: Doc }>("POST", `/api/templates/${t.id}/fill`, { values }).then((r) => setDoc(r.document)), 250);
    return () => window.clearTimeout(h);
  }, [JSON.stringify(values)]);
  const print = async () => {
    const r = await send<{ job: Job }>("POST", `/api/templates/${t.id}/fill`, { values, print: true });
    trackJob(r.job);
    moment.value = { job: r.job, img: null };
    onClose();
  };
  return (
    <Sheet open onClose={onClose} title={t.name}>
      {t.fields.map((f) => (
        <>
          <label class="field-label" for={`f-${f.key}`}>{f.label}</label>
          {f.multiline
            ? <textarea id={`f-${f.key}`} class="input" style="min-height:90px" value={values[f.key] ?? ""} onInput={(e) => setValues({ ...values, [f.key]: (e.target as HTMLTextAreaElement).value })} />
            : <input id={`f-${f.key}`} class="input" value={values[f.key] ?? ""} onInput={(e) => setValues({ ...values, [f.key]: (e.target as HTMLInputElement).value })} />}
        </>
      ))}
      <AsPrinted doc={doc} />
      <button class="btn btn-green block" style="margin-top:14px" onClick={() => print().catch((e) => toast(e.message))}>Print</button>
    </Sheet>
  );
}
