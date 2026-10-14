/** Adds the Jev page to the dashboard, shown as a tab of its own (`section`). */
import { JevPage } from "./page";
import { sdk } from "./sdk";

sdk.register("jev", {
  section: { title: "Jev", page: "jev" },
  pages: [{ id: "jev", title: "Jev", component: JevPage }],
});
