import { notFound } from "next/navigation";

import { KitExamples } from "@/ui/kit-examples";

/** Examples of the design kit. Development only: a production build answers 404. */
export default function KitPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <KitExamples />;
}
