/** Adds the conversations to the dashboard: one page, shown as a tab of its own (`section`). */
import { ConversationsPage } from "./pages/conversations";
import { sdk } from "./sdk";

sdk.register("conversations", {
  section: { title: "Hội thoại", page: "conversations" },
  pages: [{ id: "conversations", title: "Hội thoại", component: ConversationsPage }],
});
