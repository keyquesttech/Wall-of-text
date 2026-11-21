// Quick-action chips (HANDOFF 7.1): Weather now, Today's agenda, Shopping list (with count), Fortune.
// One tap prints; the shopping list chip opens the shared list so people can add to it first.
import { useEffect, useState } from "preact/hooks";
import { get, send } from "../../lib/api";
import { lastJobEvent } from "../../lib/state";
import { IconCalendar, IconCart, IconCloud, IconRefresh, IconStar } from "../../components/icons";
import { Sheet, toast } from "../../components/ui";
import { ListMode } from "./ListMode";

const CHIPS = [
  { id: "weather_now", label: "Weather now", Icon: IconCloud },
  { id: "agenda_today", label: "Today's agenda", Icon: IconCalendar },
  { id: "shopping", label: "Shopping list", Icon: IconCart },
  { id: "random_fortune", label: "Fortune", Icon: IconStar },
  { id: "reprint_last", label: "Reprint last", Icon: IconRefresh },
];

export function QuickActions() {
  const [busy, setBusy] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [list, setList] = useState(false);
  const [routines, setRoutines] = useState<{ id: string; label: string }[]>([]);
  const loadCount = () => get<{ items: { done: boolean }[] }>("/api/lists/shopping").then((r) => setCount(r.items.filter((i) => !i.done).length)).catch(() => {});
  useEffect(() => { loadCount(); }, [lastJobEvent.value?.id, list]);
  useEffect(() => { get<{ id: string; label: string }[]>("/api/actions").then((a) => setRoutines(a.filter((x) => x.id.startsWith("routine:")))).catch(() => {}); }, []);
  const run = async (id: string) => {
    setBusy(id);
    try { toast((await send<{ message: string }>("POST", `/api/actions/${encodeURIComponent(id)}`)).message); }
    catch (e) { toast((e as Error).message); }
    finally { setBusy(null); }
  };
  return (
    <>
      <div class="chips" role="group" aria-label="Quick prints">
        {CHIPS.map((c) => (
          <button class="glass chip" disabled={busy === c.id} onClick={() => (c.id === "shopping" ? setList(true) : run(c.id))}>
            <c.Icon class="i" />{c.label}{c.id === "shopping" && count > 0 && <span class="badge s">{count}</span>}
          </button>
        ))}
        {routines.map((r) => (
          <button class="glass chip" disabled={busy === r.id} onClick={() => run(r.id)}>{r.label.replace("Run routine: ", "")}</button>
        ))}
      </div>
      <Sheet open={list} onClose={() => setList(false)} title="Shopping list">
        <ListMode onPrinted={() => setList(false)} />
      </Sheet>
    </>
  );
}
