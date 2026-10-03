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
 * create form reached from the agent list, the change-password page (the original dashboard had no menu entry
 * for it either; the same section sits in the tuning page) and the dev-only kit examples.
 */
const NOT_IN_MENU = ["/", "/login", "/admin/care", "/admin/agents/new", "/admin/auth", "/dev/kit"];

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
      "Zalo & CSKH",
      "Care agent",
      "Quản trị agent",
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

describe("visibleSections", () => {
  it("hides_items_the_role_cannot_use_and_drops_empty_sections", () => {
    const sections = visibleSections((needs) => needs.includes("review.read"));

    expect(sections.map((s) => s.title)).toEqual(["Zalo & CSKH"]);
    expect(sections[0]?.items.map((i) => i.to)).toEqual(["/review"]);
  });

  it("shows_a_planned_item_in_its_place_when_the_role_has_the_permission", () => {
    const sections = visibleSections((needs) => needs.includes("appointment.read"));

    expect(sections[0]?.items.map((i) => i.to)).toContain("/schedule");
  });
});

describe("homeFor", () => {
  it("opens_the_first_screen_that_exists_and_is_allowed", () => {
    expect(homeFor((needs) => needs.includes("crm.task.read"))).toBe("/today");
  });

  it("skips_planned_screens_even_when_they_come_first", () => {
    expect(homeFor((needs) => needs.includes("appointment.read"))).toBe("/login");
  });

  it("goes_to_login_when_nothing_is_allowed", () => {
    expect(homeFor(() => false)).toBe("/login");
  });
});

describe("currentNavItem", () => {
  it("picks_the_most_specific_entry_for_a_nested_path", () => {
    expect(currentNavItem("/admin/care/matrix")?.label).toBe("Ma trận ngưỡng");
  });

  it("belongs_a_detail_page_to_its_list_entry", () => {
    expect(currentNavItem("/patients/abc")?.label).toBe("Tìm bệnh nhân");
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
