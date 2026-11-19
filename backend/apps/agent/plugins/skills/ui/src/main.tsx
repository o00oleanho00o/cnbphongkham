/** Adds the skills to the dashboard: one page, shown as a tab of its own (`section`). */
import { SkillsPage } from "./pages/skills";
import { sdk } from "./sdk";

sdk.register("skills", {
  section: { title: "Kỹ năng", page: "skills" },
  pages: [{ id: "skills", title: "Kỹ năng", component: SkillsPage }],
});
