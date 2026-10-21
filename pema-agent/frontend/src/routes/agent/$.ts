// Pema addition (plan C): runtime proxy of `/agent/v1/**` and `/agent/ui/**` to the agent service as the
// signed-in staff member. The logic and its reasons live in `@/lib/server/agent-proxy`.
import { createFileRoute } from "@tanstack/react-router";

import { forwardToAgent } from "@/lib/server/agent-proxy";

const handle = ({ request }: { request: Request }) => forwardToAgent(request);

export const Route = createFileRoute("/agent/$")({
  server: {
    handlers: {
      GET: handle,
      POST: handle,
      PUT: handle,
      PATCH: handle,
      DELETE: handle,
      HEAD: handle,
      OPTIONS: handle,
    },
  },
});
