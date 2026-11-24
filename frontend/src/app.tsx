import { useEffect } from "preact/hooks";
import { LocationProvider, Route, Router, useLocation } from "preact-iso";
import { reachable, settings, wifi } from "./lib/state";
import { IconClock, IconCreate, IconHistory, IconSettings } from "./components/icons";
import { historyBadge, PrintMoment, StatusSheet } from "./components/printer";
import { Toast } from "./components/ui";
import { Create } from "./routes/Create";
import { History } from "./routes/History";
import { Schedules, WizardHost } from "./routes/Schedules";
import { Settings } from "./routes/Settings";
import { Aside } from "./routes/Aside";
import { HOSTNAME, PRODUCT_NAME } from "./lib/config";

const TABS = [
  { href: "/", label: "Create", Icon: IconCreate, match: (p: string) => p === "/" || p.startsWith("/create") },
  { href: "/schedules", label: "Schedules", Icon: IconClock, match: (p: string) => p.startsWith("/schedules") },
  { href: "/history", label: "History", Icon: IconHistory, match: (p: string) => p.startsWith("/history") },
  { href: "/settings", label: "Settings", Icon: IconSettings, match: (p: string) => p.startsWith("/settings") },
];

function TabBar() {
  const { path } = useLocation();
  useEffect(() => { if (path.startsWith("/history")) historyBadge.value = 0; }, [path]);
  const badge = historyBadge.value;
  return (
    <div class="dock">
      <nav class="glass tabs" aria-label="Main">
        {TABS.map((t) => {
          const on = t.match(path);
          return (
            <a class={`tab ${on ? "act" : ""}`} href={t.href} aria-current={on ? "page" : undefined}>
              <t.Icon class="i" />
              <span>{t.label}</span>
              {t.href === "/history" && badge > 0 && <span class="badge" aria-label={`${badge} new`}>{badge}</span>}
            </a>
          );
        })}
      </nav>
    </div>
  );
}

function Blobs() {
  const { path } = useLocation();
  // the light leans pink on Schedules, green elsewhere (HANDOFF 4: glass picks it up)
  const sched = path.startsWith("/schedules");
  return (
    <div class="bglight" aria-hidden="true">
      <div class={`blob ${sched ? "g" : "p"}`} style="width:320px;height:320px;right:-130px;top:-70px" />
      <div class={`blob ${sched ? "p" : "g"} s`} style="width:360px;height:360px;left:-170px;bottom:40px" />
    </div>
  );
}

function Unreachable() {
  if (reachable.value) return null;
  return (
    <div class="offline-screen" role="alert">
      <div class="glass">
        <h1 class="h2">Can't reach {PRODUCT_NAME}</h1>
        <ol>
          <li>Check the printer is plugged in and its light is on.</li>
          <li>Make sure this phone is on your home Wi-Fi.</li>
          <li>Wait a minute after a power cut while it starts up.</li>
        </ol>
        <div class="row cap"><span class="dot pulse" />Looking for {HOSTNAME}{wifi.value?.ip ? ` (${wifi.value.ip})` : ""}…</div>
        <button class="btn-green" onClick={() => location.reload()}>Try again</button>
      </div>
    </div>
  );
}

/** The main column. Its width class follows the section: Create and History use wide
 *  screens; Schedules and Settings are lists and forms, so they stay at a readable width. */
function Main(props: { children: preact.ComponentChildren }) {
  const { path } = useLocation();
  const narrow = path.startsWith("/settings") || path.startsWith("/schedules");
  return <main class={`main ${narrow ? "narrow" : "wide"}`} id="main" tabIndex={-1}>{props.children}</main>;
}

function NotFound() {
  return <div class="empty"><h1 class="h2">Not found</h1><a class="btn" href="/">Go to Create</a></div>;
}

export function App() {
  useEffect(() => {
    const d = settings.value?.display;
    document.documentElement.classList.toggle("rm", !!d?.reduce_motion);
    document.documentElement.classList.toggle("solid", !!d?.reduce_transparency);
  }, [settings.value]);
  return (
    <LocationProvider>
      <a class="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <Blobs />
      <div class="app">
        <TabBar />
        <Main>
          <Router>
            <Route path="/" component={Create} />
            <Route path="/create/:mode" component={Create} />
            <Route path="/schedules/:id?/:sub?" component={Schedules} />
            <Route path="/history/:id?" component={History} />
            <Route path="/settings/:page?/:sub?" component={Settings} />
            <Route default component={NotFound} />
          </Router>
        </Main>
        <Aside />
      </div>
      <StatusSheet />
      <PrintMoment />
      <WizardHost />
      <Toast />
      <Unreachable />
    </LocationProvider>
  );
}
