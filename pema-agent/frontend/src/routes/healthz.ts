// `/healthz`: this server is up and reaches the agent (its `/health`).
import { createFileRoute } from "@tanstack/react-router";

import { agentBaseUrl } from "@/lib/server/agent-proxy";

async function handle(): Promise<Response> {
  const ok = await fetch(`${agentBaseUrl().replace(/\/+$/, "")}/health`, { cache: "no-store" })
    .then((answer) => answer.ok)
    .catch(() => false);
  return Response.json({ ok }, { status: ok ? 200 : 503, headers: { "cache-control": "no-store" } });
}

export const Route = createFileRoute("/healthz")({
  server: { handlers: { GET: handle, HEAD: handle } },
});
