import { render } from "preact";
import "../../design-handoff/tokens.css";
import "./styles.css";
import { App } from "./app";
import { boot, onServerToast } from "./lib/state";
import { toast } from "./components/ui";
import { startCrispPreviews } from "./lib/crisp";

onServerToast((m) => toast(m));
boot();
render(<App />, document.getElementById("app")!);
startCrispPreviews();
