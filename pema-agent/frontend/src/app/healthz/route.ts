// Pema addition: `/healthz` of the API through the same origin (it was a rewrite before the runtime proxy).
import { forwardToApi } from "@/lib/server/api-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Next calls a handler with (request, context); `forwardToApi`'s second parameter is not that, so wrap it.
const handle = (request: Request) => forwardToApi(request);

export const GET = handle;
export const HEAD = handle;
