import { render } from "preact";
import "./styles.css";
import { App } from "./app";
import { boot } from "./lib/state";

boot();
render(<App />, document.getElementById("app")!);
