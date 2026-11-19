// `GET /connectors`: the names of the connectors the clinic web fronts (see `./$.ts` and `connector-proxy`).
import { createFileRoute } from "@tanstack/react-router";

import { forwardToConnector } from "@/lib/server/connector-proxy";

const handle = ({ request }: { request: Request }) => forwardToConnector(request);

export const Route = createFileRoute("/connectors/")({
  server: {
    handlers: { GET: handle },
  },
});
