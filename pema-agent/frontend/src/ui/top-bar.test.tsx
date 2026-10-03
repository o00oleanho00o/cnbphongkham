// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "./top-bar";

const navigation = vi.hoisted(() => ({ pushed: [] as string[] }));

// next/navigation is the framework's router (an external dependency): record where the search goes.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: (to: string) => navigation.pushed.push(to) }),
}));

afterEach(() => {
  cleanup();
  navigation.pushed.length = 0;
});

const noop = (): void => undefined;

describe("TopBar", () => {
  it("shows_the_breadcrumb_of_the_old_web", () => {
    render(<TopBar title="Hôm nay" clinicName="Phòng khám mẫu" onOpenMenu={noop} />);

    const crumbs = screen.getByRole("navigation", { name: "Vị trí" });
    expect(crumbs.textContent).toBe("Không gian phòng khám/Hôm nay");
  });

  it("falls_back_to_CSKH_when_the_clinic_has_no_name", () => {
    render(<TopBar title="" clinicName="  " onOpenMenu={noop} />);

    expect(screen.getByText("CSKH")).toBeTruthy();
  });

  it("opens_the_menu_from_the_phone_button", async () => {
    const opened: string[] = [];
    render(<TopBar title="" clinicName="x" onOpenMenu={() => opened.push("open")} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Mở menu" }));

    expect(opened).toEqual(["open"]);
  });

  it("sends_the_patient_search_to_the_patient_list_with_the_query", async () => {
    render(<TopBar title="" clinicName="x" onOpenMenu={noop} searchHref="/patients" />);

    await userEvent
      .setup()
      .type(screen.getByRole("textbox", { name: "Tìm bệnh nhân" }), "Lan Anh{Enter}");

    expect(navigation.pushed).toEqual(["/patients?q=Lan%20Anh"]);
  });

  it("ignores_an_empty_search", async () => {
    render(<TopBar title="" clinicName="x" onOpenMenu={noop} searchHref="/patients" />);

    await userEvent
      .setup()
      .type(screen.getByRole("textbox", { name: "Tìm bệnh nhân" }), "   {Enter}");

    expect(navigation.pushed).toEqual([]);
  });

  it("has_no_search_or_bell_for_a_role_without_them", () => {
    render(<TopBar title="" clinicName="x" onOpenMenu={noop} />);

    expect(screen.queryByRole("search")).toBeNull();
    expect(screen.queryByRole("link", { name: "Mở thông báo" })).toBeNull();
  });

  it("links_the_bell_to_the_inbox", () => {
    render(<TopBar title="" clinicName="x" onOpenMenu={noop} bellHref="/inbox" />);

    expect(screen.getByRole("link", { name: "Mở thông báo" }).getAttribute("href")).toBe("/inbox");
  });
});
