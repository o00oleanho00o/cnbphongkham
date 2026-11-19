/** Adds the Connectors page to the dashboard, shown as a tab of its own (`section`). */
import { ConnectorsPage } from "./page";
import { sdk } from "./sdk";

sdk.register("connectors", {
  section: { title: "Connectors", page: "connectors" },
  pages: [{ id: "connectors", title: "Connectors", component: ConnectorsPage }],
});
