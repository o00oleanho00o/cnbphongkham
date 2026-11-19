/** Adds the knowledge store to the dashboard: one page, shown as a tab of its own (`section`). */
import { StorePage } from "./pages/store";
import { sdk } from "./sdk";

sdk.register("knowledge", {
  section: { title: "Kho tri thức", page: "store" },
  pages: [{ id: "store", title: "Kho tri thức", component: StorePage }],
});
