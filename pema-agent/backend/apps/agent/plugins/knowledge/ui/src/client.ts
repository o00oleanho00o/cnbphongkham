/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type {
  BulkAction,
  BulkResult,
  ChunkList,
  ConfirmItem,
  ConfirmResult,
  EmbeddingTest,
  Gap,
  GapState,
  JevState,
  KnowledgeSettings,
  KnowledgeStatus,
  PreviewInput,
  PreviewResult,
  SearchDebug,
  SearchDebugQuery,
  Service,
  ServiceBody,
  Source,
  SourceEvent,
  SourceList,
  SourcePatch,
  SourceQuery,
  SourceStructure,
  SettingsPatch,
} from "./types";

const BASE = "/v1/plugins/knowledge";
const id = encodeURIComponent;

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "")
    .forEach(([key, value]) => search.set(key, String(value)));
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const knowledge = {
  status: () => api.get<KnowledgeStatus>(`${BASE}/status`),

  sources: (params: SourceQuery) => api.get<SourceList>(`${BASE}/sources${query({ ...params })}`),
  source: (source: string) => api.get<Source>(`${BASE}/sources/${id(source)}`),
  updateSource: (source: string, body: SourcePatch) =>
    api.patch<Source>(`${BASE}/sources/${id(source)}`, body),
  deleteSource: (source: string) => api.del<void>(`${BASE}/sources/${id(source)}`),
  /** Approve, unapprove, change the audience, re-read or delete several sources at once. */
  bulk: (ids: readonly string[], action: BulkAction) =>
    api.post<BulkResult>(`${BASE}/sources/bulk`, { ids, ...action }),
  reindex: (source: string) => api.post<Source>(`${BASE}/sources/${id(source)}/reindex`),
  approve: (source: string) => api.post<Source>(`${BASE}/sources/${id(source)}/approve`),
  unapprove: (source: string) => api.post<Source>(`${BASE}/sources/${id(source)}/unapprove`),
  expire: (source: string) => api.post<Source>(`${BASE}/sources/${id(source)}/expire`),

  /** Reads the inputs without adding anything (no model cost). Files go as text or base64. */
  preview: (inputs: readonly PreviewInput[]) =>
    api.post<PreviewResult>(`${BASE}/sources/preview`, { inputs }),
  confirm: (previewId: string, items: readonly ConfirmItem[]) =>
    api.post<ConfirmResult>(`${BASE}/sources/confirm`, { preview_id: previewId, items }),

  structure: (source: string) => api.get<SourceStructure>(`${BASE}/sources/${id(source)}/structure`),
  saveStructure: (source: string, markdown: string) =>
    api.put<Source>(`${BASE}/sources/${id(source)}/structure`, { markdown }),
  /** Moves the sections at these outline positions into a new source (staff only until someone changes it). */
  split: (source: string, sections: readonly number[], title: string) =>
    api.post<Source>(`${BASE}/sources/${id(source)}/split`, { sections, title }),
  chunks: (source: string, params: { q?: string; page?: number }) =>
    api.get<ChunkList>(`${BASE}/sources/${id(source)}/chunks${query(params)}`),
  updateChunk: (chunk: string, body: { services?: string[]; kind?: string }) =>
    api.patch<void>(`${BASE}/chunks/${id(chunk)}`, body),
  events: (source: string) => api.get<SourceEvent[]>(`${BASE}/sources/${id(source)}/events`),
  restore: (source: string, event: string) =>
    api.post<Source>(`${BASE}/sources/${id(source)}/restore`, { event }),

  services: () => api.get<Service[]>(`${BASE}/services`),
  createService: (body: ServiceBody) => api.post<Service>(`${BASE}/services`, body),
  updateService: (service: string, body: Partial<ServiceBody>) =>
    api.patch<Service>(`${BASE}/services/${id(service)}`, body),
  deleteService: (service: string) => api.del<void>(`${BASE}/services/${id(service)}`),
  /** Reads a pasted table (CSV or Markdown) into services; nothing is saved until `importServices`. */
  importServices: (text: string) => api.post<Service[]>(`${BASE}/services/import`, { text }),

  search: (body: SearchDebugQuery) => api.post<SearchDebug>(`${BASE}/search/debug`, body),

  gaps: (state: GapState) => api.get<Gap[]>(`${BASE}/gaps${query({ state })}`),
  updateGap: (gap: string, state: GapState) => api.patch<Gap>(`${BASE}/gaps/${id(gap)}`, { state }),

  settings: () => api.get<KnowledgeSettings>(`${BASE}/settings`),
  saveSettings: (body: SettingsPatch) => api.patch<KnowledgeSettings>(`${BASE}/settings`, body),
  testEmbedding: () => api.post<EmbeddingTest>(`${BASE}/settings/test-embedding`),
  reembed: () => api.post<{ queued: number }>(`${BASE}/settings/reembed`),
};

/** Whether plugin jev is on and has a TypeSafe key, for the judging section (its own routes, not this plugin's). */
export async function jevState(): Promise<JevState> {
  const listing = await api.get<{ plugins: { name: string; enabled: boolean }[] }>("/v1/admin/plugins");
  const on = listing.plugins.some((plugin) => plugin.name === "jev" && plugin.enabled);
  if (!on) return { on, hasKey: false };
  const settings = await api.get<{ has_key: boolean }>("/v1/plugins/jev/settings");
  return { on, hasKey: settings.has_key };
}

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
