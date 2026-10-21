// The fake knowledge plugin (`/v1/plugins/knowledge/...`) for `bun run dev:mock`.
import type { Router } from "../core";
import { registerAdd } from "./add";
import { registerDetail } from "./detail";
import { registerSearch } from "./search";
import { registerServices } from "./services";
import { registerSettings } from "./settings";
import { registerSources } from "./sources";

export function registerKnowledge(router: Router): void {
  registerSources(router);
  registerAdd(router);
  registerDetail(router);
  registerServices(router);
  registerSearch(router);
  registerSettings(router);
}
