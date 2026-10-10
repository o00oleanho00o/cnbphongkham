import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { isDynamicRoute, listPageRoutes } from "../../scripts/app-routes";

import {
  NAV_SECTIONS,
  currentNavItem,
  homeFor,
  isActivePath,
  visibleSections,
  type NavItem,
} from "./nav";

const APP_DIR = fileURLToPath(new URL("../app", import.meta.url));
const items: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);
const pageRoutes = listPageRoutes(APP_DIR);

/**
 * Pages that are deliberately not menu entries: the redirect at `/`, sign-in, the index of the care tabs, the
 * change-password page (the original dashboard had no menu entry for it either), the dev-only kit examples and the tabs of the finance
 * area (one menu entry, "Tài chính & tiền thủ thuật"; the tab bar of its layout links the pages).
 */
const FINANCE_TABS = [
  "/finance/entries",
  "/finance/rates",
  "/finance/payments",
  "/finance/periods",
  "/finance/export",
];
/** Tabs of the agent entry (`/admin/agent`): its own pages, next to the pages the plugins ship. */
const AGENT_TABS = [
  "/admin/agent/overview",
  "/admin/agent/sessions",
  "/admin/agent/traces",
  "/admin/agent/model",
  "/admin/agent/plugins",
];
/**
 * Pages of the old agent layer and of the care/CSKH/clinic-administration screens, deleted (the agent's pages live
 * under `/admin/agent`; the agent is one menu entry).
 */
const REMOVED_AGENT_PAGES = [
  "/admin/overview",
  "/admin/traces",
  "/admin/threads",
  "/admin/schedules",
  "/admin/memory",
  "/admin/agents",
  "/admin/tools",
  "/admin/mcp",
  "/admin/policy",
  "/admin/tuning",
  "/admin/care",
  "/care",
  "/admin/roster",
  "/admin/kb",
  "/admin/users",
  "/admin/logs",
  "/review",
  "/templates",
];
const NOT_IN_MENU = [
  "/",
  "/login",
  "/admin/auth",
  "/me/notifications",
  "/dev/kit",
  ...FINANCE_TABS,
  ...AGENT_TABS,
];

describe("menu order of the old Pema Clinic Web", () => {
  it("opens_with_the_old_workspace_section_in_the_old_order", () => {
    const first = NAV_SECTIONS[0];

    expect(first?.title).toBe("Không gian làm việc");
    expect(first?.items.map((i) => i.to)).toEqual([
      "/dashboard",
      "/today",
      "/schedule",
      "/patients",
      "/inbox",
      "/studio",
    ]);
  });

  it("keeps_the_old_labels", () => {
    const labels = items.slice(0, 12).map((i) => i.label);

    expect(labels).toEqual([
      "Tổng quan",
      "Hôm nay",
      "Điều phối lịch",
      "Tìm bệnh nhân",
      "Theo dõi",
      "Ảnh trước / sau",
      "Bác sĩ & phòng",
      "Dịch vụ",
      "Thu ngân",
      "Tài chính & tiền thủ thuật",
      // The old web says "Ask Pema" (clinic.js); recipe U7 names the entry "Hỏi Pema" (Vietnamese UI copy).
      "Hỏi Pema",
      "Hướng dẫn",
    ]);
  });

  it("puts_the_sections_of_this_app_after_the_old_ones", () => {
    expect(NAV_SECTIONS.map((s) => s.title)).toEqual([
      "Không gian làm việc",
      "Quản lý",
      "Phân tích",
      "Agent",
    ]);
  });
});

describe("every screen stays reachable", () => {
  const staticRoutes = pageRoutes.filter((route) => !isDynamicRoute(route));

  it("lists_each_static_page_in_the_menu_unless_it_is_known_not_to_belong_there", () => {
    const inMenu = new Set(items.filter((i) => !i.planned).map((i) => i.to));

    const missing = staticRoutes.filter((r) => !inMenu.has(r) && !NOT_IN_MENU.includes(r));

    expect(missing).toEqual([]);
  });

  it("links_only_to_pages_that_exist_unless_the_item_is_marked_planned", () => {
    const dangling = items.filter((i) => !i.planned && !pageRoutes.includes(i.to)).map((i) => i.to);

    expect(dangling).toEqual([]);
  });

  it("marks_an_item_planned_only_while_its_page_is_missing", () => {
    const stale = items.filter((i) => i.planned && pageRoutes.includes(i.to)).map((i) => i.to);

    expect(stale).toEqual([]);
  });

  it("has_a_page_file_for_every_non_planned_menu_entry", () => {
    const withoutFile = items
      .filter((i) => !i.planned)
      .filter((i) => !existsSync(`${APP_DIR}/(admin)${i.to}/page.tsx`));

    expect(withoutFile.map((i) => i.to)).toEqual([]);
  });

  it("uses_each_path_once", () => {
    const paths = items.map((i) => i.to);

    expect(new Set(paths).size).toBe(paths.length);
  });
});

describe("the agent plugin pages", () => {
  const agentSection = NAV_SECTIONS.find((s) => s.title === "Agent");

  it("has_one_entry_for_the_pages_the_agent_plugins_ship", () => {
    const entry = agentSection?.items.find((i) => i.to === "/admin/agent");

    expect(entry?.label).toBe("Điều khiển agent");
    expect(entry?.needs).toEqual(["admin.agents"]);
  });

  it("has_no_page_and_no_menu_entry_left_of_the_removed_agent_layer", () => {
    const paths = items.map((i) => i.to);
    const covered = (route: string) =>
      REMOVED_AGENT_PAGES.some((gone) => route === gone || route.startsWith(`${gone}/`));

    expect(paths.filter(covered)).toEqual([]);
    expect(pageRoutes.filter(covered)).toEqual([]);
    expect(paths).toContain("/admin/agent");
  });

  it("drops_the_zalo_pages_the_plugin_pages_replace", () => {
    const paths = items.map((i) => i.to);

    for (const gone of ["/admin/accounts", "/admin/friends", "/admin/contacts"]) {
      expect(paths).not.toContain(gone);
    }
  });

  it("belongs_every_plugin_page_to_the_plugin_entry_but_not_the_agents_list", () => {
    expect(currentNavItem("/admin/agent/plugins/zalo/accounts")?.label).toBe("Điều khiển agent");
    expect(currentNavItem("/admin/agent/model")?.label).toBe("Điều khiển agent");
    expect(currentNavItem("/admin/agents")).toBeUndefined();
  });
});

describe("visibleSections", () => {
  it("hides_items_the_role_cannot_use_and_drops_empty_sections", () => {
    const sections = visibleSections((needs) => needs.includes("admin.agents"));

    expect(sections.map((s) => s.title)).toEqual(["Agent"]);
    expect(sections[0]?.items.map((i) => i.to)).toEqual(["/admin/agent"]);
  });

  it("shows_a_planned_item_in_its_place_when_the_role_has_the_permission", () => {
    const sections = visibleSections((needs) => needs.includes("appointment.read"));

    expect(sections[0]?.items.map((i) => i.to)).toContain("/schedule");
  });
});

const ACCOUNTANT_PERMISSIONS = [
  "patient.read",
  "consent.read",
  "order.read",
  "order.write",
  "finance.read",
  "finance.write",
  "finance_period.close",
  "finance.collect",
  "kb.read",
] as const;

describe("the accountant menu", () => {
  it("shows_the_pages_of_the_old_accountant_and_none_of_the_inbox_the_crm_or_the_queue", () => {
    const granted = new Set<string>(ACCOUNTANT_PERMISSIONS);
    const paths = visibleSections((needs) => needs.some((p) => granted.has(p)))
      .flatMap((s) => s.items)
      .map((i) => i.to);

    expect(paths).toEqual(expect.arrayContaining(["/patients", "/cashier", "/finance", "/guide"]));
    for (const hidden of ["/today", "/inbox", "/crm", "/dashboard", "/schedule", "/studio"]) {
      expect(paths).not.toContain(hidden);
    }
  });
});

describe("homeFor", () => {
  it("opens_the_first_screen_that_exists_and_is_allowed", () => {
    expect(homeFor((needs) => needs.includes("crm.task.read"))).toBe("/dashboard");
    expect(homeFor((needs) => needs.includes("appointment.read"))).toBe("/dashboard");
  });

  it("sends_the_care_role_to_the_cskh_queue_like_the_old_web", () => {
    const care = new Set(["crm.task.read", "crm.task.resolve", "appointment.read"]);

    expect(homeFor((needs) => needs.some((p) => care.has(p)))).toBe("/today");
  });

  it("opens_finance_for_a_role_that_holds_only_the_personal_finance_view", () => {
    expect(homeFor((needs) => needs.includes("finance.read_own"))).toBe("/finance");
  });

  it("opens_the_cashier_for_the_accountant_like_the_old_web", () => {
    const accountant = new Set<string>(ACCOUNTANT_PERMISSIONS);

    expect(homeFor((needs) => needs.some((p) => accountant.has(p)))).toBe("/cashier");
  });

  it("does_not_send_a_role_with_a_schedule_to_the_cashier", () => {
    const manager = new Set<string>([...ACCOUNTANT_PERMISSIONS, "appointment.read"]);

    expect(homeFor((needs) => needs.some((p) => manager.has(p)))).toBe("/dashboard");
  });

  it("has_no_planned_screen_left_to_skip", () => {
    expect(items.filter((i) => i.planned).map((i) => i.to)).toEqual([]);
  });

  it("goes_to_login_when_nothing_is_allowed", () => {
    expect(homeFor(() => false)).toBe("/login");
  });
});

describe("currentNavItem", () => {
  it("picks_the_most_specific_entry_for_a_nested_path", () => {
    expect(currentNavItem("/admin/agent/plugins/zalo/accounts")?.label).toBe("Điều khiển agent");
  });

  it("belongs_a_detail_page_to_its_list_entry", () => {
    expect(currentNavItem("/patients/abc")?.label).toBe("Tìm bệnh nhân");
  });

  it("belongs_every_finance_screen_to_the_finance_entry", () => {
    expect(currentNavItem("/finance")?.label).toBe("Tài chính & tiền thủ thuật");
    expect(currentNavItem("/finance/periods")?.label).toBe("Tài chính & tiền thủ thuật");
  });

  it("belongs_the_order_review_and_print_pages_to_the_cashier_entry", () => {
    expect(currentNavItem("/orders/abc")?.label).toBe("Thu ngân");
    expect(currentNavItem("/orders/abc/print")?.label).toBe("Thu ngân");
  });

  it("is_undefined_for_a_path_outside_the_menu", () => {
    expect(currentNavItem("/nowhere")).toBeUndefined();
  });
});

describe("isActivePath", () => {
  it("matches_the_path_itself_and_its_children_but_not_a_longer_sibling", () => {
    expect(isActivePath("/admin/agents", "/admin/agents")).toBe(true);
    expect(isActivePath("/admin/agents/x", "/admin/agents")).toBe(true);
    expect(isActivePath("/admin/agents-old", "/admin/agents")).toBe(false);
  });
});
