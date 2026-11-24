import { useEffect, useState } from "preact/hooks";
import { useLocation, useRoute } from "preact-iso";
import { api, send } from "../lib/api";
import { auth, printer, settings, wifi } from "../lib/state";
import { STATE_TEXT, StatusPill } from "../components/printer";
import { HOSTNAME, PRODUCT_NAME } from "../lib/config";
import { Banner, Chevron, Group, Sheet, toast, ToggleRow, Topbar } from "../components/ui";
import { GuestAndInbox, SETTINGS_PAGES } from "./settings/pages";

const MODES: Record<string, string> = { online: "Connected", connecting: "Connecting", setup_ap: "Setup network", fallback_ap: "Can't find your Wi-Fi" };

export function Settings() {
  const { params } = useRoute();
  // Calendars and Google Tasks used to be separate pages; both live on the Google page now.
  const page = ["calendars", "tasks"].includes(params.page ?? "") ? "google" : params.page || "";
  const P = SETTINGS_PAGES.find((p) => p.id === page);
  if (P) return <P.Component />;
  return <SettingsIndex />;
}

function SettingsIndex() {
  const a = auth.value;
  const p = printer.value;
  const w = wifi.value;
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.device().then(setD).catch(() => {}); }, []);
  const pct = p?.paper_percent ?? 100;
  const up = d ? (d.uptime_s >= 86400 ? `up ${Math.floor(d.uptime_s / 86400)} day${d.uptime_s >= 172800 ? "s" : ""}` : `up ${Math.floor(d.uptime_s / 3600)} h`) : "";
  const groups = SETTINGS_PAGES.reduce<string[]>((acc, x) => (acc.includes(x.group) ? acc : [...acc, x.group]), []);
  return (
    <>
      <Topbar title="Settings"><StatusPill /></Topbar>
      {a?.default_password_in_use && <Banner action={<a class="btn" href="/settings/access">Change</a>}>You're still using the default password.</Banner>}
      <div class="glass tg devcard">
        <div class="row" style="gap:14px">
          <div class="devglyph" aria-hidden="true"><i /><span class={p?.state === "offline" ? "dot grey" : p?.state === "paper_out" ? "dot pink" : "dot"} /></div>
          <div class="grow" style="display:flex;flex-direction:column">
            <span class="h3">{PRODUCT_NAME}</span>
            <span class="cap">{STATE_TEXT[p?.state ?? "ready"]} · {w?.hostname ?? HOSTNAME}</span>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px">
          <div class="row" style="justify-content:space-between"><span style="font-size:13px">Paper roll</span><span class="num" style="font-size:13px;color:var(--hi);font-weight:600">About {pct}% left</span></div>
          <div class={`bar ${pct <= 10 ? "pk" : ""}`}><i style={{ width: `${pct}%` }} /></div>
        </div>
        {d && <span class="cap">Pi {d.temperature_c != null ? `${Math.round(d.temperature_c)} °C` : "—"} · {d.throttled.flags.some((f: string) => !f.endsWith("since_boot")) ? "throttled" : "running cool"} · {up}</span>}
      </div>
      {groups.map((g) => (
        <Group label={g}>
          {SETTINGS_PAGES.filter((x) => x.group === g).map((x) => (
            <a class="lrow" href={`/settings/${x.id}`}>
              <span class="ico">{x.Icon ? <x.Icon class="i" /> : null}</span>
              {x.title}
              {x.meta && <span class="v">{x.meta()}</span>}
              <Chevron />
            </a>
          ))}
        </Group>
      ))}
      <button class="btn" onClick={() => send("POST", "/api/auth/logout").finally(() => location.replace("/signin"))}>Sign out</button>
    </>
  );
}

export function useBack() {
  const { route } = useLocation();
  return () => route("/settings");
}

// ---------------------------------------------------------------- Wi-Fi --
export function WifiPage() {
  const back = useBack();
  const w = wifi.value;
  const [confirm, setConfirm] = useState(false);
  const [gone, setGone] = useState(false);
  if (gone) {
    return (<><Topbar title="Starting setup" /><p>The printer is leaving your Wi-Fi. Join the <b>WallOfText-Setup</b> network to set it up again.</p></>);
  }
  return (
    <>
      <Topbar title="Wi-Fi" back={back} />
      <div class="glass">
        <dl class="kv">
          <dt>Status</dt><dd>{MODES[w?.mode ?? "online"]}</dd>
          <dt>Network</dt><dd>{w?.ssid ?? "—"}</dd>
          <dt>Signal</dt><dd>{w?.signal != null ? `${w.signal}%` : "—"}</dd>
          <dt>IP address</dt><dd class="mono">{w?.ip ?? "—"}</dd>
          <dt>Address</dt><dd class="mono">http://{w?.hostname}</dd>
        </dl>
      </div>
      <p class="dim small" style="margin:10px 6px">If walloftext.local doesn't open on a phone, use the IP address instead.</p>
      <div class="stack" style="margin-top:14px">
        <button class="btn" onClick={() => location.assign("/setup")}>Change network</button>
        <button class="btn" onClick={() => send("POST", "/api/print/setup-slip").then(() => toast("Printing the setup slip")).catch((e) => toast(e.message))}>Print setup slip</button>
        <button class="btn btn-danger" onClick={() => setConfirm(true)}>Forget this network and start setup again</button>
      </div>
      <Sheet open={confirm} onClose={() => setConfirm(false)} title="Forget this Wi-Fi?">
        <p>The printer will leave your home network and disappear from it until it's set up again. It starts the WallOfText-Setup network and prints a setup slip.</p>
        <div class="stack">
          <button class="btn btn-pink" onClick={() => send("POST", "/api/wifi/reset", { confirm: true }).then(() => { setConfirm(false); setGone(true); })}>Forget and start setup</button>
          <button class="btn" onClick={() => setConfirm(false)}>Cancel</button>
        </div>
      </Sheet>
    </>
  );
}

// --------------------------------------------------------------- Access --
function PwField(props: { id: string; label: string; value: string; onInput: (v: string) => void; auto?: string }) {
  const [show, setShow] = useState(false);
  return (
    <>
      <label class="field-label" for={props.id}>{props.label}</label>
      <div style="position:relative">
        <input id={props.id} class="input" type={show ? "text" : "password"} value={props.value} autoComplete={props.auto ?? "off"}
          onInput={(e) => props.onInput((e.target as HTMLInputElement).value)} style="padding-right:70px" />
        <button type="button" class="btn btn-ghost small" style="position:absolute;right:4px;top:6px" aria-pressed={show} onClick={() => setShow(!show)}>{show ? "Hide" : "Show"}</button>
      </div>
    </>
  );
}

export function AccessPage() {
  const back = useBack();
  const a = auth.value;
  const [cur, setCur] = useState(""), [nw, setNw] = useState(""), [conf, setConf] = useState("");
  const [apCur, setApCur] = useState(""), [apNew, setApNew] = useState("");
  const [msg, setMsg] = useState<{ k: "info" | "error"; t: string } | null>(null);
  const [apMsg, setApMsg] = useState<{ k: "info" | "error"; t: string } | null>(null);
  const refresh = () => api.auth().then((x) => (auth.value = x));
  useEffect(() => { refresh(); }, []);
  const changePw = async (e: Event) => {
    e.preventDefault();
    if (nw !== conf) return setMsg({ k: "error", t: "The new passwords don't match." });
    try {
      await send("POST", "/api/auth/password", { current: cur, new: nw });
      setMsg({ k: "info", t: "Password changed. Other devices are signed out." });
      setCur(""); setNw(""); setConf(""); refresh();
    } catch (err) { setMsg({ k: "error", t: (err as Error).message }); }
  };
  const changeAp = async (e: Event) => {
    e.preventDefault();
    try {
      await send("POST", "/api/auth/setup-wifi-password", { current_password: apCur, new: apNew });
      setApMsg({ k: "info", t: "Setup Wi-Fi password changed. It applies the next time the setup network starts." });
      setApCur(""); setApNew(""); refresh();
    } catch (err) { setApMsg({ k: "error", t: (err as Error).message }); }
  };
  return (
    <>
      <Topbar title="Access" back={back} />
      {a?.password_file_warning && <Banner>{a.password_file_warning}</Banner>}
      {a?.default_password_in_use && <Banner>You're still using the default password.</Banner>}
      {a?.default_setup_wifi_password_in_use && <Banner kind="warn">You're still using the default setup Wi-Fi password.</Banner>}
      <div class="glass grp">
        <ToggleRow label="Ask for password" sub="Anyone on your Wi-Fi needs the password to use the printer." checked={a?.ask_for_password ?? true}
          onChange={(v) => send("POST", "/api/auth/ask-for-password", { ask_for_password: v }).then(refresh)} />
      </div>
      <h2 class="section">Password</h2>
      <form class="glass card" onSubmit={changePw}>
        {msg && <Banner kind={msg.k === "info" ? "info" : undefined}>{msg.t}</Banner>}
        <PwField id="pw-cur" label="Current password" value={cur} onInput={setCur} auto="current-password" />
        <PwField id="pw-new" label="New password (4 to 64 characters)" value={nw} onInput={setNw} auto="new-password" />
        <PwField id="pw-conf" label="Confirm new password" value={conf} onInput={setConf} auto="new-password" />
        <button class="btn btn-green block" style="margin-top:16px" disabled={!cur || !nw}>Change password</button>
        <p class="dim tiny" style="margin:10px 4px 0">Changing it signs out every other device.</p>
      </form>
      <h2 class="section">Setup Wi-Fi password</h2>
      <form class="glass card" onSubmit={changeAp}>
        {apMsg && <Banner kind={apMsg.k === "info" ? "info" : undefined}>{apMsg.t}</Banner>}
        <p class="dim small" style="margin:0">The password of the WallOfText-Setup network, which appears only during setup or when the printer loses your Wi-Fi. Changing it re-keys that network. 8 to 63 characters.</p>
        <PwField id="ap-cur" label="Your site password" value={apCur} onInput={setApCur} auto="current-password" />
        <PwField id="ap-new" label="New setup Wi-Fi password" value={apNew} onInput={setApNew} auto="new-password" />
        <button class="btn btn-green block" style="margin-top:16px" disabled={!apCur || apNew.length < 8}>Change setup Wi-Fi password</button>
      </form>
      <p class="dim tiny" style="margin:14px 6px">Both passwords are stored as plain text on the printer and typed over plain HTTP on your home network. Treat them as a household lock, not strong security.</p>
      {settings.value && <GuestAndInbox />}
    </>
  );
}
