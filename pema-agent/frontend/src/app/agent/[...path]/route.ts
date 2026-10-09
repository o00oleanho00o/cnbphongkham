// Pema addition (plan C): runtime proxy of `/agent/v1/**` and `/agent/ui/**` to the agent service as the
// signed-in staff member. The logic and its reasons live in `@/lib/server/agent-proxy`.
import { forwardToAgent } from "@/lib/server/agent-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const handle = (request: Request) => forwardToAgent(request);

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
export const OPTIONS = handle;
