// Settings sub-pages, grouped as in Settings. Later phases add groups here.
import type { FunctionComponent } from "preact";
import { AccessPage, WifiPage } from "../Settings";
import { wifi } from "../../lib/state";

export interface SettingsPage {
  id: string;
  title: string;
  group: string;
  Component: FunctionComponent;
  meta?: () => string;
}

export const SETTINGS_PAGES: SettingsPage[] = [
  { id: "wifi", title: "Wi-Fi", group: "Device", Component: WifiPage, meta: () => wifi.value?.ssid ?? "" },
  { id: "access", title: "Access", group: "Access", Component: AccessPage },
];
