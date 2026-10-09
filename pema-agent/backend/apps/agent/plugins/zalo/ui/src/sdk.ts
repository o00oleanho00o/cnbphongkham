/** The dashboard's SDK: it sets `window.__PEMA_AGENT__` up before it loads this script. */
import type { Sdk } from "../../../web/ui/src/sdk";

const found = window.__PEMA_AGENT__;
if (!found) throw new Error("The Zalo pages run inside the Pema Agent dashboard");

export const sdk: Sdk = found;
export const { api, ui } = found;
