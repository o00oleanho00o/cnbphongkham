// Runtime proxy of `/connectors/<name>/v1/**` and `/connectors/<name>/ui/**` to a connector service as the signed-in
// staff member, and `GET /connectors` (the names). The logic and its reasons live in `@/lib/server/connector-proxy`.
import { createFileRoute } from "@tanstack/react-router";

import { forwardToConnector } from "@/lib/server/connector-proxy";

const handle = ({ request }: { request: Request }) => forwardToConnector(request);

export const Route = createFileRoute("/connectors/$")({
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
