// Settings › Email and Settings › Telegram: remote messages (BUILD_PLAN 9.2).
import { useEffect, useState } from "preact/hooks";
import { get, send } from "../../lib/api";
import { IconPlus, IconTrash } from "../../components/icons";
import { Banner, Seg, Sheet, timeAgo, toast, Toggle, Topbar } from "../../components/ui";
import { useBack } from "../Settings";

interface Channel {
  id: string; label: string; enabled: boolean; configured: boolean;
  status: "ok" | "cant_connect" | "reauth" | "off"; message: string | null; last_ok: number | null; settings: any;
}
interface Sender { id: string; name: string; identifiers: { channel: string; value: string }[]; approval: "print" | "approve" }

const STATUS: Record<string, string> = { ok: "Connected", cant_connect: "Can't connect", reauth: "Sign in again", off: "Off" };

/** Settings › Email: the printer's own inbox, and the people allowed to email it. */
export function EmailPage() {
  const back = useBack();
  const [c, setC] = useState<Channel | null>(null);
  const [blocked, setBlocked] = useState(0);
  const [senders, setSenders] = useState<Sender[]>([]);
  const [editing, setEditing] = useState<Sender | "new" | null>(null);
  const [addr, setAddr] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [host, setHost] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => {
    get<{ channels: Channel[]; blocked_week: number }>("/api/remote/channels").then((r) => { setC(r.channels.find((x) => x.id === "email") ?? null); setBlocked(r.blocked_week); });
    get<{ items: Sender[] }>("/api/remote/senders").then((r) => setSenders(r.items.filter((x) => x.identifiers.some((i) => i.channel === "email"))));
  };
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  if (!c) return (<><Topbar title="Email" back={back} /><div class="shim" style="height:160px" /></>);
  const address = addr ?? c.settings.address ?? "";
  const imap = host ?? c.settings.imap_host ?? "imap.gmail.com";
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await send("PATCH", "/api/remote/channels/email", { credentials: { address, imap_host: imap, ...(pw ? { app_password: pw } : {}) } });
      const r = await send<{ message: string }>("POST", "/api/remote/channels/email/test");
      await send("PATCH", "/api/remote/channels/email", { enabled: true });
      setMsg({ ok: true, t: r.message }); setPw(""); load();
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); } finally { setBusy(false); }
  };
  const status = !c.configured ? "Not set up" : c.enabled ? STATUS[c.status] + (c.last_ok ? ` · checked ${timeAgo(c.last_ok)}` : "") : "Off";
  return (
    <>
      <Topbar title="Email" back={back} />
      <p class="cap" style="margin:-4px 4px 0">Email the printer from anywhere and it prints on the wall. It only checks its own inbox; nothing is opened up to the internet, and only people you allow are printed.</p>

      <h2 class="section">Connection</h2>
      {c.enabled && c.status !== "ok" && c.message && <Banner>{c.message}</Banner>}
      {msg && <Banner kind={msg.ok ? "info" : undefined}>{msg.t}</Banner>}
      <div class="glass grp">
        <div class="lrow">
          <div class="grow"><div class="title">{c.settings.address || "The printer's inbox"}</div><div class="sub">{status}</div></div>
          {c.configured && <Toggle label="Email on" checked={c.enabled} onChange={(v) => send("PATCH", "/api/remote/channels/email", { enabled: v }).then(load)} />}
        </div>
        <div class="lrow col">
          {!c.configured && (
            <ol class="small dim" style="padding-left:20px;margin:0">
              <li>Make a new personal Gmail account just for the printer (Google Workspace accounts won't work).</li>
              <li>Turn on 2-Step Verification for it.</li>
              <li>Create an app password (Google Account › Security › App passwords).</li>
              <li>Enter the address and app password below.</li>
            </ol>
          )}
          <label class="field-label" for="eaddr" style="margin-top:4px">Printer's email address</label>
          <input id="eaddr" class="input" type="email" value={address} placeholder="printer@gmail.com" onInput={(e) => setAddr((e.target as HTMLInputElement).value)} />
          <label class="field-label" for="epw">App password {c.settings.has_password && <span>(saved; leave blank to keep)</span>}</label>
          <input id="epw" class="input" type="password" autoComplete="off" value={pw} placeholder="xxxx xxxx xxxx xxxx" onInput={(e) => setPw((e.target as HTMLInputElement).value)} />
          <details><summary class="dim small" style="min-height:44px;display:flex;align-items:center">Not Gmail?</summary>
            <label class="field-label" for="ehost">IMAP server</label>
            <input id="ehost" class="input" value={imap} onInput={(e) => setHost((e.target as HTMLInputElement).value)} />
          </details>
          <button class="btn btn-green block" disabled={busy || !address || (!pw && !c.settings.has_password)} onClick={save}>{busy ? "Checking…" : c.configured ? "Save and test" : "Connect"}</button>
        </div>
      </div>
      <p class="dim tiny" style="margin:8px 6px">The printer checks this inbox every minute. Only mail that passes the sender's SPF or DKIM check counts, so a faked From address is ignored.</p>

      <h2 class="section">People</h2>
      <div class="glass grp">
        {senders.length === 0 && <div class="lrow dim">Nobody yet. Email from anyone else is dropped.</div>}
        {senders.map((x) => (
          <button class="lrow" onClick={() => setEditing(x)}>
            <div class="grow"><div class="title">{x.name}</div><div class="sub">{x.identifiers.filter((i) => i.channel === "email").map((i) => i.value).join(" · ")}</div></div>
            <span class="meta">{x.approval === "approve" ? "Waits for OK" : "Prints straight away"}</span>
          </button>
        ))}
        <button class="lrow" onClick={() => setEditing("new")}><IconPlus width={18} /><span class="grow">Add a person</span></button>
      </div>
      {blocked > 0 && <p class="dim tiny" style="margin:8px 6px">{blocked} message{blocked === 1 ? "" : "s"} from people not on a list {blocked === 1 ? "was" : "were"} dropped this week (email and Telegram).</p>}
      {c.configured && (
        <button class="btn btn-ghost btn-danger block" style="margin-top:16px" onClick={() => send("DELETE", "/api/remote/channels/email/credentials").then(() => { setAddr(null); load(); })}>Remove the email details</button>
      )}
      {editing && <SenderSheet sender={editing === "new" ? null : editing} channel="email" onClose={() => { setEditing(null); load(); }} />}
    </>
  );
}

function SenderSheet(props: { sender: Sender | null; channel?: "email" | "telegram"; onClose: () => void }) {
  const s = props.sender;
  const [name, setName] = useState(s?.name ?? "");
  const [ids, setIds] = useState<{ channel: string; value: string }[]>(s?.identifiers ?? [{ channel: props.channel ?? "email", value: "" }]);
  const [approval, setApproval] = useState<"print" | "approve">(s?.approval ?? "print");
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    try {
      const body = { name, identifiers: ids.filter((i) => i.value.trim()), approval };
      if (s) await send("PATCH", `/api/remote/senders/${s.id}`, body);
      else await send("POST", "/api/remote/senders", body);
      props.onClose();
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Sheet open onClose={props.onClose} title={s ? s.name : "Add a person"}>
      {err && <Banner>{err}</Banner>}
      <label class="field-label" for="sn">Name to print</label>
      <input id="sn" class="input" value={name} maxLength={40} onInput={(e) => setName((e.target as HTMLInputElement).value)} />
      <label class="field-label">How they send</label>
      <div class="stack">
        {ids.map((i, k) => (
          <div class="row">
            <select class="input" style="width:130px" value={i.channel} aria-label="Channel" onChange={(e) => setIds(ids.map((x, j) => (j === k ? { ...x, channel: (e.target as HTMLSelectElement).value } : x)))}>
              <option value="email">Email</option><option value="telegram">Telegram ID</option>
            </select>
            <input class="input grow" value={i.value} aria-label="Address or ID" placeholder={i.channel === "email" ? "name@example.com" : "Use Add someone on the Telegram page"}
              onInput={(e) => setIds(ids.map((x, j) => (j === k ? { ...x, value: (e.target as HTMLInputElement).value } : x)))} />
            <button class="icon-btn" aria-label="Remove" onClick={() => setIds(ids.filter((_, j) => j !== k))}><IconTrash /></button>
          </div>
        ))}
        <button class="btn small" onClick={() => setIds([...ids, { channel: "email", value: "" }])}><IconPlus width={16} />Another address</button>
      </div>
      <label class="field-label">Their messages</label>
      <Seg label="Approval" value={approval} onChange={setApproval} options={[{ value: "print", label: "Print straight away" }, { value: "approve", label: "Wait for my OK" }]} />
      <button class="btn btn-green block" style="margin-top:18px" disabled={!name.trim() || !ids.some((i) => i.value.trim())} onClick={save}>Save</button>
      {s && <button class="btn btn-ghost btn-danger block" style="margin-top:8px" onClick={() => send("DELETE", `/api/remote/senders/${s.id}`).then(props.onClose)}>Remove {s.name}</button>}
    </Sheet>
  );
}

/** Telegram connection for Settings › Telegram: bot token, on/off, status, and "Add me". */
export function TelegramConnection() {
  const [c, setC] = useState<Channel | null>(null);
  const [senders, setSenders] = useState<Sender[]>([]);
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pairing, setPairing] = useState<any>(null);
  const [pairName, setPairName] = useState("");
  const [editing, setEditing] = useState<Sender | null>(null);
  const load = () => {
    get<{ channels: Channel[] }>("/api/remote/channels").then((r) => setC(r.channels.find((x) => x.id === "telegram") ?? null));
    get<{ items: Sender[] }>("/api/remote/senders").then((r) => setSenders(r.items.filter((x) => x.identifiers.some((i) => i.channel === "telegram"))));
  };
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!pairing?.active) return;
    const t = setInterval(() => get<any>("/api/remote/pairing").then(setPairing), 2000);
    return () => clearInterval(t);
  }, [pairing?.active]);
  if (!c) return <div class="shim" style="height:120px" />;
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      if (token) await send("PATCH", "/api/remote/channels/telegram", { credentials: { bot_token: token } });
      const r = await send<{ message: string }>("POST", "/api/remote/channels/telegram/test");
      await send("PATCH", "/api/remote/channels/telegram", { enabled: true });
      setMsg({ ok: true, t: r.message }); setToken(""); load();
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); } finally { setBusy(false); }
  };
  const status = !c.configured ? "Not set up" : c.enabled ? STATUS[c.status] + (c.last_ok ? ` · checked ${timeAgo(c.last_ok)}` : "") : "Off";
  return (
    <>
      <h2 class="section">Connection</h2>
      {c.enabled && c.status !== "ok" && c.message && <Banner>{c.message}</Banner>}
      {msg && <Banner kind={msg.ok ? "info" : undefined}>{msg.t}</Banner>}
      <div class="glass grp">
        <div class="lrow">
          <div class="grow"><div class="title">{c.settings.bot_username ? `@${c.settings.bot_username}` : "Your bot"}</div><div class="sub">{status}</div></div>
          {c.configured && <Toggle label="Telegram on" checked={c.enabled} onChange={(v) => send("PATCH", "/api/remote/channels/telegram", { enabled: v }).then(load)} />}
        </div>
        <div class="lrow col">
          {!c.configured && (
            <ol class="small dim" style="padding-left:20px;margin:0">
              <li>In Telegram, message <b>@BotFather</b> and send <span class="mono">/newbot</span>.</li>
              <li>Pick a name; BotFather replies with a token. Paste it below.</li>
            </ol>
          )}
          <label class="field-label" for="ttok" style="margin-top:4px">Bot token {c.settings.has_token && <span>(saved; leave blank to keep)</span>}</label>
          <input id="ttok" class="input" type="password" autoComplete="off" value={token} placeholder="123456:ABC-…" onInput={(e) => setToken((e.target as HTMLInputElement).value)} />
          <button class="btn btn-green block" disabled={busy || (!token && !c.settings.has_token)} onClick={save}>{busy ? "Checking…" : c.configured ? "Save and test" : "Connect"}</button>
        </div>
      </div>

      {c.configured && (
        <>
          <h2 class="section">People</h2>
          <div class="glass grp">
            {senders.length === 0 && <div class="lrow dim">Nobody can message the bot yet.</div>}
            {senders.map((x) => (
              <button class="lrow" onClick={() => setEditing(x)}>
                <div class="grow"><div class="title">{x.name}</div><div class="sub">ID {x.identifiers.find((i) => i.channel === "telegram")?.value}</div></div>
                <span class="meta">{x.approval === "approve" ? "Waits for OK" : "Prints straight away"}</span>
              </button>
            ))}
            {!pairing?.captured && (
              <button class="lrow" disabled={pairing?.active} onClick={() => send<any>("POST", "/api/remote/pairing/start").then(setPairing).catch((e) => toast(e.message))}>
                <IconPlus width={18} /><span class="grow">{pairing?.active ? `Send the bot a message now… ${pairing.seconds_left}s` : "Add someone (they message the bot)"}</span>
              </button>
            )}
          </div>
          {pairing?.captured && (
            <div class="glass card" style="margin-top:12px">
              <p style="margin-top:0">Got a message from <b>{pairing.captured.name}</b> (ID {pairing.captured.user_id}). Allow them?</p>
              <label class="field-label" for="pname">Name to print</label>
              <input id="pname" class="input" value={pairName || pairing.captured.name} onInput={(e) => setPairName((e.target as HTMLInputElement).value)} />
              <button class="btn btn-green block" style="margin-top:12px" onClick={() => send("POST", "/api/remote/pairing/confirm", { name: pairName || pairing.captured.name }).then(() => { toast("Added"); setPairing(null); setPairName(""); load(); })}>Yes, allow</button>
            </div>
          )}
          <p class="dim tiny" style="margin:8px 6px">Tap Add someone, then they send the bot any message within 5 minutes. People who also email the printer show on the <a href="/settings/email" style="color:var(--green);text-decoration:underline">Email</a> page too.</p>
        </>
      )}
      {editing && <SenderSheet sender={editing} onClose={() => { setEditing(null); load(); }} />}
    </>
  );
}

/** Remove the bot token (bottom of the Telegram page). */
export function TelegramRemove() {
  const [has, setHas] = useState(false);
  useEffect(() => { get<{ channels: Channel[] }>("/api/remote/channels").then((r) => setHas(!!r.channels.find((x) => x.id === "telegram")?.configured)); }, []);
  if (!has) return null;
  return <button class="btn btn-ghost btn-danger block" style="margin-top:16px" onClick={() => send("DELETE", "/api/remote/channels/telegram/credentials").then(() => location.reload())}>Disconnect the bot</button>;
}
