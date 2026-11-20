// Phase 6
import { useBack } from "../Settings";
import { Topbar } from "../../components/ui";

export function RemotePage() {
  const back = useBack();
  return (<><Topbar title="Remote messages" back={back} /><div class="empty">Coming soon.</div></>);
}
