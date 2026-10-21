import { createFileRoute, redirect } from "@tanstack/react-router";

/** The shell decides where a role lands (see `homeFor` in `lib/nav.ts`); `/today` is the default. */
export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/today" });
  },
});
