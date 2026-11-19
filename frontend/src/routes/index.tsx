import { createFileRoute, redirect } from "@tanstack/react-router";

/** The agent dashboard is the only area. */
export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/admin/agent" });
  },
});
