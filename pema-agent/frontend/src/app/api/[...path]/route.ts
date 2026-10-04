// Pema addition: runtime proxy of `/api/v1/**` to the API (replaces the build-time `rewrites()` of next.config.ts).
// The logic and its reasons live in `@/lib/server/api-proxy`; this file only binds the HTTP methods.
import { forwardToApi } from "@/lib/server/api-proxy";

// Never cache, never prerender: the API address and the session cookie are per request.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Next calls a handler with (request, context); `forwardToApi`'s second parameter is not that, so wrap it.
const handle = (request: Request) => forwardToApi(request);

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
export const OPTIONS = handle;
