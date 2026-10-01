import { redirect } from "next/navigation";

/** The shell decides where a role lands (see `homeFor` in `lib/nav.ts`); `/today` is the default. */
export default function Home() {
  redirect("/today");
}
