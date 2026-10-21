// Pema addition: runtime proxy of `/api/v1/**` to the API (replaces the build-time `rewrites()` of the Next.js config).
// The logic and its reasons live in `@/lib/server/api-proxy`; this file only binds the HTTP methods.
import { createFileRoute } from "@tanstack/react-router";

import { forwardToApi } from "@/lib/server/api-proxy";

// `forwardToApi`'s second parameter is not the handler context, so wrap it.
const handle = ({ request }: { request: Request }) => forwardToApi(request);

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
