// Connector proxy (docs/PLAN-zalo-service.md section 5, docs/CONNECTOR-PROTOCOL.md section 5): the same-origin proxy
// from the browser to a connector's own admin API and pages, as `agent-proxy.ts` is for the agent.
//
// `/connectors/<name>/v1/**` and `/connectors/<name>/ui/**` go to `<address of that connector>/v1/**` and `/ui/**`
// with the short token the clinic API issues for the signed-in staff member (the same token, cache, permission check,
// header rules and path rules as the agent proxy: they are its functions). `GET /connectors` answers the names, so the
// pages' host knows which connectors to ask for their scripts. Addresses come from `PEMA_CONNECTOR_URLS`, a comma list
// of `name=url` (`zalo=http://zalo:8089`), read on every request.

import { type Env, errorResponse, parseHttpUrl } from "@/lib/server/api-proxy";
import {
  type AgentForwardOptions,
  forwardResolved,
  resolveUnder,
  sessionOf,
  sharedTokens,
} from "@/lib/server/agent-proxy";

export const CONNECTORS_PREFIX = "/connectors";
const NAME = /^[a-z0-9_-]{1,32}$/;

/** The connectors named in `PEMA_CONNECTOR_URLS` (`name=url,name=url`); an entry that is not valid is left out. */
export function connectorUrls(env: Env = process.env): Map<string, string> {
  const entries = (env.PEMA_CONNECTOR_URLS ?? "").split(",").flatMap((entry) => {
    const at = entry.indexOf("=");
    const name = entry.slice(0, at).trim();
    const url = entry.slice(at + 1).trim();
    return at > 0 && NAME.test(name) && parseHttpUrl(url) ? [[name, url] as const] : [];
  });
  return new Map(entries);
}

const BAD_LIST_METHOD = "Chỉ đọc được danh sách connector bằng GET.";

/** Forward one request to a connector as the signed-in staff member, or answer the list of connectors. */
export async function forwardToConnector(
  request: Request,
  options: AgentForwardOptions = {},
): Promise<Response> {
  const env = options.env ?? process.env;
  const incoming = new URL(request.url);

  // Signed in first, so an anonymous caller cannot learn which connectors are configured.
  const session = sessionOf(request.headers.get("cookie"));
  if (!session) return errorResponse(401, "unauthenticated", "Bạn cần đăng nhập.");

  const urls = connectorUrls(env);
  const rest = incoming.pathname.slice(CONNECTORS_PREFIX.length).replace(/^\/+/, "");
  if (rest === "") return listConnectors(request, session, urls, options);

  const name = rest.split("/")[0] ?? "";
  const base = urls.get(name);
  if (base === undefined) return errorResponse(404, "not_found", "Không tìm thấy connector này.");
  const prefixPath = `${CONNECTORS_PREFIX}/${name}`;
  const resolved = resolveUnder(prefixPath, incoming.pathname, incoming.search, base);
  return forwardResolved(
    request,
    resolved,
    { base, prefixPath, label: `connector ${name}` },
    options,
  );
}

/** `GET /connectors` → `{connectors: [names]}`; the token request is the permission check, no connector is called. */
async function listConnectors(
  request: Request,
  session: string,
  urls: Map<string, string>,
  options: AgentForwardOptions,
): Promise<Response> {
  if (request.method !== "GET") return errorResponse(405, "validation_failed", BAD_LIST_METHOD);
  const token = await (options.tokens ?? sharedTokens).get(
    session,
    options.env ?? process.env,
    options.fetchImpl ?? fetch,
  );
  if (!token.ok) return token.response;
  return Response.json({ connectors: [...urls.keys()] }, { headers: { "cache-control": "no-store" } });
}
