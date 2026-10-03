// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { NavSection } from "@/lib/nav";
import type { UserSummary } from "@/lib/session/session-context";
import { IconCalendar } from "@/ui/icons";

import { Sidebar } from "./sidebar";

// next/navigation is the framework's router (an external dependency): the guarded links read it.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => undefined }) }));

beforeAll(() => {
  // jsdom has no matchMedia; the theme hook of the footer listens to it.
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => cleanup());

const SECTIONS: NavSection[] = [
  {
    title: "Không gian làm việc",
    items: [
      { to: "/today", label: "Hôm nay", icon: IconCalendar, needs: ["crm.task.read"] },
      {
        to: "/schedule",
        label: "Điều phối lịch",
        icon: IconCalendar,
        needs: ["appointment.read"],
        planned: true,
      },
    ],
  },
  {
    title: "Care agent",
    items: [
      {
        to: "/care/handoffs",
        label: "Yêu cầu chuyển giao",
        icon: IconCalendar,
        needs: ["care.read"],
      },
    ],
  },
];

const USER = {
  display_name: "Người dùng mẫu",
  role: "reception",
  clinic_name: "Phòng khám mẫu",
} as UserSummary;

const noop = (): void => undefined;

function renderSidebar(pathname: string, mobileOpen = false) {
  return render(
    <Sidebar
      sections={SECTIONS}
      pathname={pathname}
      online={null}
      user={USER}
      onLogout={noop}
      mobileOpen={mobileOpen}
      onCloseMobile={noop}
    />,
  );
}

describe("Sidebar", () => {
  it("lists_the_sections_and_their_items_in_order", () => {
    renderSidebar("/today");

    const nav = screen.getByRole("navigation", { name: "Chức năng" });
    expect(
      within(nav)
        .getAllByText(/Không gian làm việc|Care agent/)
        .map((n) => n.textContent),
    ).toEqual(["Không gian làm việc", "Care agent"]);
    expect(
      within(nav)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(["/today", "/care/handoffs"]);
  });

  it("marks_the_current_screen", () => {
    renderSidebar("/today");

    expect(screen.getByRole("link", { name: "Hôm nay" }).getAttribute("aria-current")).toBe("page");
    expect(
      screen.getByRole("link", { name: "Yêu cầu chuyển giao" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("keeps_a_planned_screen_in_place_as_text_that_is_not_a_link", () => {
    renderSidebar("/today");

    expect(screen.queryByRole("link", { name: /Điều phối lịch/ })).toBeNull();
    expect(screen.getByText("Điều phối lịch").parentElement?.getAttribute("aria-disabled")).toBe(
      "true",
    );
    expect(screen.getByText("(sắp có)")).toBeTruthy();
  });

  it("shows_the_clinic_mark_and_who_is_signed_in", () => {
    renderSidebar("/today");

    expect(screen.getByAltText("Pema")).toBeTruthy();
    expect(screen.getByText("PHÒNG KHÁM DA LIỄU")).toBeTruthy();
    expect(screen.getByText("Người dùng mẫu")).toBeTruthy();
    expect(screen.getByText(/Lễ tân · Phòng khám mẫu/)).toBeTruthy();
  });

  it("closes_the_drawer_when_a_link_is_followed", async () => {
    const closed: string[] = [];
    render(
      <Sidebar
        sections={SECTIONS}
        pathname="/today"
        online={null}
        user={USER}
        onLogout={noop}
        mobileOpen
        onCloseMobile={() => closed.push("closed")}
      />,
    );

    // jsdom cannot navigate: stop the default action once the link has handled the click
    document.addEventListener("click", (e) => e.preventDefault(), { once: true });
    await userEvent.setup().click(screen.getByRole("link", { name: "Yêu cầu chuyển giao" }));

    expect(closed).toEqual(["closed"]);
  });

  it("offers_the_sign_out_and_theme_buttons", () => {
    renderSidebar("/today");

    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Đổi giao diện sáng/tối" })).toBeTruthy();
  });
});
