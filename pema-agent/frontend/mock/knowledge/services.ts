// Routes of the fake knowledge store: the services catalogue (the backbone of the labels) and "Nhập từ bảng", which
// really reads the pasted CSV / Markdown table with the same function the page uses to list unreadable lines.
import type { Service, ServiceBody } from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import {
  codeProblem,
  normaliseCode,
  parseServiceTable,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/services/services-logic";
import { type Reply, type Router, bodyOf } from "../core";
import { nextId, store } from "./store";

const BASE = "/v1/plugins/knowledge/services";
const NOT_FOUND: Reply = { status: 404, body: { detail: "Không tìm thấy dịch vụ này." } };

const refuse = (status: number, detail: string): Reply => ({ status, body: { detail } });

/** Why a body cannot be saved (the server checks again whatever the page checked), or null. */
function problemOf(body: ServiceBody, ownId: string | null): string | null {
  const code = codeProblem(normaliseCode(body.code ?? ""), store.services, ownId);
  if (code) return code;
  return (body.name ?? "").trim() === "" ? "Nhập tên dịch vụ." : null;
}

const cleanBody = (body: ServiceBody): ServiceBody => ({
  code: normaliseCode(body.code),
  name: body.name.trim(),
  aliases: body.aliases ?? [],
  description: (body.description ?? "").trim(),
  branches: body.branches ?? [],
  enabled: body.enabled ?? true,
});

/** Sources carry service codes: a renamed or deleted code follows into them. */
function renameInSources(from: string, to: string | null): void {
  store.sources = store.sources.map((source) => {
    if (!source.services.includes(from)) return source;
    const rest = source.services.filter((code) => code !== from);
    return { ...source, services: to === null || rest.includes(to) ? rest : [...rest, to] };
  });
}

function create(body: ServiceBody): Reply {
  const problem = problemOf(body, null);
  if (problem) return refuse(422, problem);
  const service: Service = { ...cleanBody(body), id: nextId("svc"), chunk_count: 0 };
  store.services = [...store.services, service];
  return { status: 201, body: service };
}

function update(id: string | undefined, patch: Partial<ServiceBody>): Reply {
  const found = store.services.find((service) => service.id === id);
  if (!found) return NOT_FOUND;
  const merged = cleanBody({ ...found, ...patch });
  const problem = problemOf(merged, found.id);
  if (problem) return refuse(422, problem);
  const next: Service = { ...found, ...merged };
  store.services = store.services.map((service) => (service.id === next.id ? next : service));
  if (next.code !== found.code) renameInSources(found.code, next.code);
  return { body: next };
}

function remove(id: string | undefined): Reply {
  const found = store.services.find((service) => service.id === id);
  if (!found) return NOT_FOUND;
  store.services = store.services.filter((service) => service.id !== found.id);
  renameInSources(found.code, null);
  return { status: 204 };
}

/** The rows that could be read, as services the page can show; nothing is saved. */
function preview(text: string): Service[] {
  return parseServiceTable(text).rows.map((row) => ({
    ...row,
    id: `preview-${row.code}`,
    chunk_count: store.services.find((service) => service.code === row.code)?.chunk_count ?? 0,
  }));
}

export function registerServices(router: Router): void {
  router.get(BASE, null, (): Reply => ({ body: store.services }));
  router.post(BASE, null, (ctx): Reply => create(bodyOf<ServiceBody>(ctx)));
  router.post(`${BASE}/import`, null, (ctx): Reply => {
    const { text } = bodyOf<{ text?: string }>(ctx);
    return { body: preview(text ?? "") };
  });
  router.patch(`${BASE}/{id}`, null, (ctx): Reply => update(ctx.params.id, bodyOf<Partial<ServiceBody>>(ctx)));
  router.delete(`${BASE}/{id}`, null, (ctx): Reply => remove(ctx.params.id));
}
