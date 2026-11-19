// `/api/v1/**`: the sign-in routes the screens call, answered here with the agent's own logins (`agent-auth.ts`).
import { createFileRoute } from "@tanstack/react-router";

import { answerAuth } from "@/lib/server/agent-auth";

const handle = ({ request }: { request: Request }) => answerAuth(request);

export const Route = createFileRoute("/api/$")({
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
