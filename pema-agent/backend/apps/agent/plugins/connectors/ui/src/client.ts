/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type { Connector, Created } from "./types";

const BASE = "/v1/plugins/connectors";

export const connectors = {
  list: () => api.get<{ connectors: Connector[] }>(`${BASE}/`).then((found) => found.connectors),
  create: (name: string) => api.post<Created>(`${BASE}/`, { name }),
  revoke: (name: string) => api.del<{ revoked: string }>(`${BASE}/${encodeURIComponent(name)}`),
};

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
