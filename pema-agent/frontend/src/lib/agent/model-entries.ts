// The list of models the agent keeps ready (`/v1/admin/model/entries`): several keys of the same provider side by
// side, one in use. The rules the Model page shows them by: which provider brand a model belongs to, the label a new
// one gets, and the grouping of the list.
import { MODEL_PRESETS } from "@/lib/agent/model-presets";

export const ENTRIES_PATH = "/v1/admin/model/entries";

export interface ModelEntry {
  id: string;
  label: string;
  provider: string;
  model: string;
  base_url: string | null;
  reasoning: string | null;
  dialect: string | null;
  /** Masked: the key itself never comes back. */
  api_key: string;
  has_key: boolean;
  api_key_broken: boolean;
  active: boolean;
}

export interface EntryGroup {
  brand: string;
  entries: ModelEntry[];
}

const OTHER_BRAND = "Khác";

export const entryPath = (id: string, action = "") =>
  `${ENTRIES_PATH}/${id}${action ? `/${action}` : ""}`;

function hostOf(address: string | null): string {
  if (!address) return "";
  try {
    return new URL(address).host;
  } catch {
    return "";
  }
}

/** The provider the model belongs to, by its address (DeepSeek, OpenAI...); an unknown address names itself. */
export function brandOf(entry: Pick<ModelEntry, "provider" | "base_url">): string {
  const host = hostOf(entry.base_url);
  const preset = MODEL_PRESETS.find((item) =>
    host ? hostOf(item.base_url) === host : item.provider === entry.provider && !item.base_url,
  );
  return preset?.label ?? (host || OTHER_BRAND);
}

/** The label offered for a new model of a provider: its name, then "DeepSeek 2", "DeepSeek 3"... counting the
 * models of that provider already in the list, and never a label already taken. */
export function nextLabel(brand: string, entries: readonly ModelEntry[]): string {
  const taken = new Set(entries.map((entry) => entry.label));
  const known = entries.filter((entry) => brandOf(entry) === brand).length;
  const numbered = (number: number) => (number === 1 ? brand : `${brand} ${number}`);
  const free = Array.from({ length: entries.length + 1 }, (_, index) =>
    numbered(known + 1 + index),
  ).find((label) => !taken.has(label));
  return free ?? brand;
}

/** The list grouped by provider, in the order each provider first appears. */
export function groupByBrand(entries: readonly ModelEntry[]): EntryGroup[] {
  return entries.reduce<EntryGroup[]>((groups, entry) => {
    const brand = brandOf(entry);
    const found = groups.find((group) => group.brand === brand);
    if (!found) return [...groups, { brand, entries: [entry] }];
    return groups.map((group) =>
      group === found ? { ...group, entries: [...group.entries, entry] } : group,
    );
  }, []);
}

/** "3 DeepSeek · 4 OpenAI": how many models of each provider the list holds. */
export function brandCounts(entries: readonly ModelEntry[]): string {
  return groupByBrand(entries)
    .map((group) => `${group.entries.length} ${group.brand}`)
    .join(" · ");
}
