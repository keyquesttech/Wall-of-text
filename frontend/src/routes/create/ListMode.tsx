// The List: one shared checklist everyone on the Wi-Fi adds to; printing it empties it (a one-off print).
import { useEffect, useMemo, useState } from "preact/hooks";
import { get, send, type Doc, type Job } from "../../lib/api";
import { lastJobEvent } from "../../lib/state";
import { IconPlus, IconTrash } from "../../components/icons";
import { AsPrinted, startMoment } from "../../components/printer";
import { toast } from "../../components/ui";

interface Item { id: number; text: string; done: boolean }

export function ListMode(props: { onPrinted?: () => void } = {}) {
  const [items, setItems] = useState<Item[]>([]);
  const [text, setText] = useState("");
  const load = () => get<{ items: Item[] }>("/api/lists/shopping").then((r) => setItems(r.items));
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);
  useEffect(() => { load(); }, [lastJobEvent.value?.id]);
  const add = async (e: Event) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setText("");
    await send("POST", "/api/lists/shopping", { text: t });
    load();
  };
  const open = items.filter((i) => !i.done);
  const done = items.filter((i) => i.done);
  // the same slip the printer makes (server-rendered "As printed" preview)
  const doc: Doc = useMemo(() => ({ blocks: [{ type: "slip", template: "shopping", data: { items: open.map((i) => i.text) } }] } as unknown as Doc),
    [open.map((i) => i.text).join("\n")]);
  return (
    <>
      <form class="row" onSubmit={add} style="margin:8px 0 12px">
        <input class="input grow" value={text} maxLength={120} placeholder="Add to the list" aria-label="New item"
          onInput={(e) => setText((e.target as HTMLInputElement).value)} />
        <button class="ib tile" aria-label="Add"><IconPlus class="i" /></button>
      </form>
      <div class="glass grp">
        {open.length === 0 && <div class="lrow dim">The list is empty.</div>}
        {open.map((i) => <Row i={i} onChange={load} />)}
      </div>
      {done.length > 0 && (
        <>
          <h2 class="section">Got it</h2>
          <div class="glass grp">{done.map((i) => <Row i={i} onChange={load} />)}</div>
          <button class="btn btn-ghost block" style="margin-top:8px" onClick={() => send("POST", "/api/lists/shopping/clear-done").then(load)}>Clear ticked items</button>
        </>
      )}
      {open.length > 0 && (
        <>
          <h2 class="section">As printed</h2>
          <div style="margin-top:8px"><AsPrinted doc={doc} /></div>
        </>
      )}
      <button class="btn-green block" style="margin-top:16px;width:100%" disabled={open.length === 0} onClick={async () => {
        try {
          const r = await send<{ job: Job }>("POST", "/api/lists/shopping/print");
          startMoment(r.job, null);
          toast("Printing. The list empties once the slip is out.");
          props.onPrinted?.();
        } catch (e) { toast((e as Error).message); }
      }}>Print the list</button>
      <p class="dim tiny" style="margin:10px 6px">Anyone signed in on your Wi-Fi can add to this list. When you print it, the printed items are removed once the slip comes out; ticked items and anything added meanwhile stay.</p>
    </>
  );
}

function Row({ i, onChange }: { i: Item; onChange: () => void }) {
  return (
    <div class="lrow">
      <input type="checkbox" checked={i.done} aria-label={`${i.text} ${i.done ? "ticked" : ""}`} style="width:22px;height:22px;accent-color:var(--green)"
        onChange={() => send("PATCH", `/api/lists/items/${i.id}`, { done: !i.done }).then(onChange)} />
      <span class="grow" style={i.done ? "text-decoration:line-through;color:var(--c-dim)" : ""}>{i.text}</span>
      <button class="ib" aria-label={`Remove ${i.text}`} onClick={() => send("DELETE", `/api/lists/items/${i.id}`).then(onChange)}><IconTrash /></button>
    </div>
  );
}
