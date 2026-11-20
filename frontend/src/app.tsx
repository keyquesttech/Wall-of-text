import { useEffect } from "preact/hooks";
import { LocationProvider, Route, Router, useLocation } from "preact-iso";
import { pendingJobs, reachable, settings, wifi } from "./lib/state";
import { IconClock, IconCreate, IconHistory, IconSettings, IconWifiOff } from "./components/icons";
import { PrintMoment, StatusSheet } from "./components/printer";
import { Toast } from "./components/ui";
import { Create } from "./routes/Create";
import { History } from "./routes/History";
import { Schedules } from "./routes/Schedules";
import { Settings } from "./routes/Settings";
import { Aside } from "./routes/Aside";
import { PRODUCT_NAME } from "./lib/config";

const TABS = [
  { href: "/", label: "Create", Icon: IconCreate, match: (p: string) => p === "/" || p.startsWith("/create") },
  { href: "/schedules", label: "Schedules", Icon: IconClock, match: (p: string) => p.startsWith("/schedules") },
  { href: "/history", label: "History", Icon: IconHistory, match: (p: string) => p.startsWith("/history") },
  { href: "/settings", label: "Settings", Icon: IconSettings, match: (p: string) => p.startsWith("/settings") },
];

function TabBar() {
  const { path } = useLocation();
  const waiting = pendingJobs.value.length;
  return (
    <nav class="tabbar" aria-label="Main">
      {TABS.map((t) => (
        <a class="tab" href={t.href} aria-current={t.match(path) ? "page" : undefined}>
          <t.Icon />
          {t.label}
          {t.href === "/history" && waiting > 0 && <span class="badge" aria-label={`${waiting} waiting`}>{waiting}</span>}
        </a>
      ))}
    </nav>
  );
}

function Unreachable() {
  if (reachable.value) return null;
  return (
    <div class="offline-screen" role="alert">
      <IconWifiOff />
      <h1>Can't reach {PRODUCT_NAME}</h1>
      <p class="dim" style="max-width:340px">Check the printer is switched on and that this device is on the same Wi-Fi. This page reconnects by itself.</p>
      {wifi.value?.ip && <p class="dim small">Last known address: http://{wifi.value.ip}/</p>}
      <button class="btn" onClick={() => location.reload()}>Try again</button>
    </div>
  );
}

function NotFound() {
  return <div class="empty"><h1>Not found</h1><a class="btn" href="/">Go to Create</a></div>;
}

export function App() {
  useEffect(() => {
    const d = settings.value?.display;
    document.documentElement.classList.toggle("rm", !!d?.reduce_motion);
    document.documentElement.classList.toggle("solid", !!d?.reduce_transparency);
  }, [settings.value]);
  return (
    <LocationProvider>
      <div class="app">
        <TabBar />
        <main class="main" id="main">
          <Router>
            <Route path="/" component={Create} />
            <Route path="/create/:mode" component={Create} />
            <Route path="/schedules/:id?/:sub?" component={Schedules} />
            <Route path="/history/:id?" component={History} />
            <Route path="/settings/:page?/:sub?" component={Settings} />
            <Route default component={NotFound} />
          </Router>
        </main>
        <Aside />
      </div>
      <StatusSheet />
      <PrintMoment />
      <Toast />
      <Unreachable />
    </LocationProvider>
  );
}
