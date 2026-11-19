/** The dashboard's SDK: it sets `window.__CONTETE_AGENT__` up before it loads this script. */
import type { Sdk } from "../../../web/ui/src/sdk";

const found = window.__CONTETE_AGENT__;
if (!found) throw new Error("The Jev page runs inside the Contete Agent dashboard");

export const sdk: Sdk = found;
export const { api, ui } = found;
