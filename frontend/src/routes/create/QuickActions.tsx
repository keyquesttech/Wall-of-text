// Quick-action chips: the same actions the button gestures run (BUILD_PLAN 8).
import { useEffect, useState } from "preact/hooks";
import { get, send } from "../../lib/api";
import { IconBolt } from "../../components/icons";
import { toast } from "../../components/ui";

const SHOWN = ["random_fortune", "weather_now", "agenda_today", "shopping_list", "reprint_last"];
const SHORT: Record<string, string> = {
  random_fortune: "Fortune", weather_now: "Weather", agenda_today: "Agenda", shopping_list: "Shopping list", reprint_last: "Reprint last",
};

export function QuickActions() {
  const [acts, setActs] = useState<{ id: string; label: string }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { get<{ id: string; label: string }[]>("/api/actions").then(setActs).catch(() => {}); }, []);
  const list = acts.filter((a) => SHOWN.includes(a.id) || a.id.startsWith("routine:"));
  if (!list.length) return null;
  return (
    <div class="chips" role="group" aria-label="Quick prints">
      {list.map((a) => (
        <button class="chip" disabled={busy === a.id} onClick={async () => {
          setBusy(a.id);
          try { toast((await send<{ message: string }>("POST", `/api/actions/${encodeURIComponent(a.id)}`)).message); }
          catch (e) { toast((e as Error).message); }
          finally { setBusy(null); }
        }}>
          <IconBolt width={14} height={14} />{SHORT[a.id] ?? a.label.replace("Run routine: ", "")}
        </button>
      ))}
    </div>
  );
}
