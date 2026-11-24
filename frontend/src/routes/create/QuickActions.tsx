// Quick-action chips (HANDOFF 7.1): Weather now, Today's agenda, Fortune, Reprint last and routines.
// One tap prints. (The List lives in its own Create mode.)
import { useEffect, useState } from "preact/hooks";
import { get, send } from "../../lib/api";
import { IconCalendar, IconCloud, IconRefresh, IconStar } from "../../components/icons";
import { toast } from "../../components/ui";

const CHIPS = [
  { id: "weather_now", label: "Weather now", Icon: IconCloud },
  { id: "agenda_today", label: "Today's agenda", Icon: IconCalendar },
  { id: "random_fortune", label: "Fortune", Icon: IconStar },
  { id: "reprint_last", label: "Reprint last", Icon: IconRefresh },
];

export function QuickActions() {
  const [busy, setBusy] = useState<string | null>(null);
  const [routines, setRoutines] = useState<{ id: string; label: string }[]>([]);
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
          <button class="glass chip" disabled={busy === c.id} onClick={() => run(c.id)}>
            <c.Icon class="i" />{c.label}
          </button>
        ))}
        {routines.map((r) => (
          <button class="glass chip" disabled={busy === r.id} onClick={() => run(r.id)}>{r.label.replace("Run routine: ", "")}</button>
        ))}
      </div>
    </>
  );
}
