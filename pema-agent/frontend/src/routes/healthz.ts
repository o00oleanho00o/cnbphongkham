// Pema addition: `/healthz` of the API through the same origin.
import { createFileRoute } from "@tanstack/react-router";

import { forwardToApi } from "@/lib/server/api-proxy";

const handle = ({ request }: { request: Request }) => forwardToApi(request);

export const Route = createFileRoute("/healthz")({
  server: { handlers: { GET: handle, HEAD: handle } },
});
