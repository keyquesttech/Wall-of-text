// Settings › Messages › Remote messages (BUILD_PLAN 9.2). DESIGN REVIEW: new screen.
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
const CH_LABEL: Record<string, string> = { email: "Email", telegram: "Telegram", sms: "Phone", mock: "Test" };

export function RemotePage() {
  const back = useBack();
  const [chs, setChs] = useState<Channel[]>([]);
  const [blocked, setBlocked] = useState(0);
  const [senders, setSenders] = useState<Sender[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<Sender | "new" | null>(null);
  const load = () => {
    get<{ channels: Channel[]; blocked_week: number }>("/api/remote/channels").then((r) => { setChs(r.channels); setBlocked(r.blocked_week); });
    get<{ items: Sender[] }>("/api/remote/senders").then((r) => setSenders(r.items));
  };
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  return (
    <>
      <Topbar title="Remote messages" back={back} />
      <p class="dim small" style="margin:0 6px 12px">Send a message from anywhere and it prints on the wall. The printer only ever checks out to the internet; nothing is opened up to it. Only people on your allowed list get printed.</p>
      <div class="glass grp">
        {chs.map((c) => (
          <button class="lrow" onClick={() => setOpen(c.id)}>
            <div class="grow">
              <div class="title">{c.label}</div>
              <div class="sub">{!c.configured ? "Not set up" : c.enabled ? STATUS[c.status] + (c.last_ok ? ` · checked ${timeAgo(c.last_ok)}` : "") : "Off"}</div>
            </div>
            {c.enabled && c.status !== "ok" && c.configured && <span class="state-tag failed">{STATUS[c.status]}</span>}
          </button>
        ))}
        <div class="lrow"><div class="grow"><div class="title">Text message (SMS)</div><div class="sub" style="white-space:normal">Needs a paid phone number or a SIM modem. Not set up in this version.</div></div></div>
      </div>
      {blocked > 0 && <p class="dim small" style="margin:8px 6px">{blocked} message{blocked === 1 ? "" : "s"} from people not on the list {blocked === 1 ? "was" : "were"} blocked this week.</p>}

      <h2 class="section">Allowed senders</h2>
      <div class="glass grp">
        {senders.length === 0 && <div class="lrow dim">Nobody yet. Messages from anyone else are dropped.</div>}
        {senders.map((s) => (
          <button class="lrow" onClick={() => setEditing(s)}>
            <div class="grow">
              <div class="title">{s.name}</div>
              <div class="sub">{s.identifiers.map((i) => `${CH_LABEL[i.channel] ?? i.channel}: ${i.value}`).join(" · ")}</div>
            </div>
            <span class="meta">{s.approval === "approve" ? "Waits for OK" : "Prints straight away"}</span>
          </button>
        ))}
        <button class="lrow" onClick={() => setEditing("new")}><IconPlus width={18} /><span class="grow">Add a person</span></button>
      </div>
      {open && <ChannelSheet ch={chs.find((c) => c.id === open)!} senders={senders} onClose={() => { setOpen(null); load(); }} />}
      {editing && <SenderSheet sender={editing === "new" ? null : editing} onClose={() => { setEditing(null); load(); }} />}
    </>
  );
}

function ChannelSheet(props: { ch: Channel; senders: Sender[]; onClose: () => void }) {
  const c = props.ch;
  const [addr, setAddr] = useState(c.settings.address ?? "");
  const [pw, setPw] = useState("");
  const [host, setHost] = useState(c.settings.imap_host ?? "imap.gmail.com");
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pairing, setPairing] = useState<any>(null);
  const [pairName, setPairName] = useState("");
  useEffect(() => {
    if (!pairing?.active) return;
    const t = setInterval(() => get<any>("/api/remote/pairing").then(setPairing), 2000);
    return () => clearInterval(t);
  }, [pairing?.active]);
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const creds: any = c.id === "email" ? { address: addr, imap_host: host, ...(pw ? { app_password: pw } : {}) } : token ? { bot_token: token } : {};
      await send("PATCH", `/api/remote/channels/${c.id}`, { credentials: creds });
      const r = await send<{ message: string }>("POST", `/api/remote/channels/${c.id}/test`);
      await send("PATCH", `/api/remote/channels/${c.id}`, { enabled: true });
      setMsg({ ok: true, t: r.message }); setPw(""); setToken("");
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={props.onClose} title={c.label}>
      {c.enabled && c.status !== "ok" && c.message && <Banner>{c.message}</Banner>}
      {msg && <Banner kind={msg.ok ? "info" : undefined}>{msg.t}</Banner>}
      {c.configured && (
        <div class="glass grp" style="margin-bottom:12px">
          <div class="lrow"><span class="grow">On</span><Toggle label={`${c.label} on`} checked={c.enabled} onChange={(v) => send("PATCH", `/api/remote/channels/${c.id}`, { enabled: v }).then(props.onClose)} /></div>
        </div>
      )}
      {c.id === "email" && (
        <>
          <ol class="small dim" style="padding-left:20px;margin-top:0">
            <li>Make a new personal Gmail account just for the printer (Google Workspace accounts won't work).</li>
            <li>Turn on 2-Step Verification for it.</li>
            <li>Create an app password (Google Account › Security › App passwords).</li>
            <li>Enter the address and app password here. Then email that address from anywhere.</li>
          </ol>
          <label class="field-label" for="eaddr">Printer's email address</label>
          <input id="eaddr" class="input" type="email" value={addr} placeholder="ourwallprinter@gmail.com" onInput={(e) => setAddr((e.target as HTMLInputElement).value)} />
          <label class="field-label" for="epw">App password {c.settings.has_password && <span>(saved; leave blank to keep)</span>}</label>
          <input id="epw" class="input" type="password" autoComplete="off" value={pw} placeholder="xxxx xxxx xxxx xxxx" onInput={(e) => setPw((e.target as HTMLInputElement).value)} />
          <details style="margin-top:10px"><summary class="dim small">Not Gmail?</summary>
            <label class="field-label" for="ehost">IMAP server</label>
            <input id="ehost" class="input" value={host} onInput={(e) => setHost((e.target as HTMLInputElement).value)} />
          </details>
          <p class="dim tiny">The printer checks this inbox every minute. Only mail that passes the sender's SPF or DKIM check counts, so a faked From address is ignored.</p>
          <button class="btn btn-green block" disabled={busy || !addr || (!pw && !c.settings.has_password)} onClick={save}>{busy ? "Checking…" : "Save and test"}</button>
        </>
      )}
      {c.id === "telegram" && (
        <>
          <ol class="small dim" style="padding-left:20px;margin-top:0">
            <li>In Telegram, message <b>@BotFather</b> and send <span class="mono">/newbot</span>.</li>
            <li>Pick a name; BotFather replies with a token. Paste it here.</li>
            <li>Press <b>Add me</b>, then send your new bot any message within 5 minutes.</li>
          </ol>
          <label class="field-label" for="ttok">Bot token {c.settings.has_token && <span>(saved; leave blank to keep)</span>}</label>
          <input id="ttok" class="input" type="password" autoComplete="off" value={token} placeholder="123456:ABC-…" onInput={(e) => setToken((e.target as HTMLInputElement).value)} />
          {c.settings.bot_username && <p class="dim small">Your bot: <span class="mono">@{c.settings.bot_username}</span></p>}
          {c.configured && <a class="btn block" style="margin-top:10px" href="/settings/telegram">Commands, templates and print style</a>}
          <button class="btn btn-green block" style="margin-top:12px" disabled={busy || (!token && !c.settings.has_token)} onClick={save}>{busy ? "Checking…" : "Save and test"}</button>
          {c.configured && !pairing?.captured && (
            <button class="btn block" style="margin-top:10px" disabled={pairing?.active} onClick={() => send<any>("POST", "/api/remote/pairing/start").then(setPairing).catch((e) => toast(e.message))}>
              {pairing?.active ? `Waiting for your message… ${pairing.seconds_left}s` : "Add me"}
            </button>
          )}
          {pairing?.captured && (
            <div class="glass card" style="margin-top:12px">
              <p style="margin-top:0">Got a message from <b>{pairing.captured.name}</b> (ID {pairing.captured.user_id}). Is that you?</p>
              <label class="field-label" for="pname">Name to print</label>
              <input id="pname" class="input" value={pairName || pairing.captured.name} onInput={(e) => setPairName((e.target as HTMLInputElement).value)} />
              <button class="btn btn-green block" style="margin-top:12px" onClick={() => send("POST", "/api/remote/pairing/confirm", { name: pairName || pairing.captured.name }).then(() => { toast("Added to allowed senders"); props.onClose(); })}>Yes, allow</button>
            </div>
          )}
          <p class="dim tiny" style="margin-top:12px">The bot replies "Printed" when your message comes out.</p>
        </>
      )}
      {c.id === "mock" && <p class="dim">Drop JSON files into <span class="mono">{c.settings.folder}</span> or POST to /api/dev/inbound.</p>}
      {c.configured && c.id !== "mock" && (
        <button class="btn btn-ghost btn-danger block" style="margin-top:12px" onClick={() => send("DELETE", `/api/remote/channels/${c.id}/credentials`).then(props.onClose)}>Remove {c.label} details</button>
      )}
    </Sheet>
  );
}

function SenderSheet(props: { sender: Sender | null; onClose: () => void }) {
  const s = props.sender;
  const [name, setName] = useState(s?.name ?? "");
  const [ids, setIds] = useState<{ channel: string; value: string }[]>(s?.identifiers ?? [{ channel: "email", value: "" }]);
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
              <option value="email">Email</option><option value="telegram">Telegram ID</option><option value="sms">Phone</option>
            </select>
            <input class="input grow" value={i.value} aria-label="Address or ID" placeholder={i.channel === "email" ? "name@example.com" : i.channel === "telegram" ? "Use Add me in Telegram" : "+44…"}
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
