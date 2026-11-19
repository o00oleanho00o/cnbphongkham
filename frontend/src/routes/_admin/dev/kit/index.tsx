import { createFileRoute, notFound } from "@tanstack/react-router";

import { KitExamples } from "@/ui/kit-examples";

/** Examples of the design kit. Development only: a production build answers 404. */
function KitPage() {
  return <KitExamples />;
}

export const Route = createFileRoute("/_admin/dev/kit/")({
  beforeLoad: () => {
    if (import.meta.env.PROD) throw notFound();
  },
  component: KitPage,
});
