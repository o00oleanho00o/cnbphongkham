// @vitest-environment jsdom
// The shell of the finance area (`/finance/*`): the header of the old page ("ĐIỀU HÀNH • PEMA CLINIC", the title,
// "Kỳ báo cáo", "Làm mới"), the tabs each role sees (the accountant six, a doctor three), the month in the address,
// the owner's switch between "Toàn phòng khám" and "Cá nhân", and what a role without finance access is told.
// There is no role picker: the projection comes from the session.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFinance } from "@/components/finance/finance-context";
import { ACCOUNTANT, DOCTOR, OWNER } from "@/components/finance/test-support";
import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import FinanceLayout from "./layout";

const nav = vi.hoisted(() => ({
  search: "",
  pathname: "/finance",
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function Probe() {
  const { month, scope, canWrite, refreshKey } = useFinance();
  return (
    <p data-testid="probe">
      {month}|{scope}|{String(canWrite)}|{refreshKey}
    </p>
  );
}

function renderShell(
  permissions: Permission[],
  role: "owner" | "manager" | "doctor",
  child?: ReactNode,
) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Người dùng",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <FinanceLayout>{child ?? <Probe />}</FinanceLayout>
      </ToastProvider>
    </SessionProvider>,
  );
}

const tabNames = () =>
  within(screen.getByRole("navigation", { name: "Phân hệ tài chính" }))
    .getAllByRole("link")
    .map((a) => a.textContent);

beforeEach(() => {
  nav.search = "month=2026-09";
  nav.pathname = "/finance";
  nav.replace.mockReset();
});

afterEach(() => cleanup());

describe("the header of the old page", () => {
  it("keeps_the_eyebrow_the_title_the_month_picker_and_the_refresh_button", () => {
    renderShell(ACCOUNTANT, "manager");

    expect(screen.getByText("ĐIỀU HÀNH • PEMA CLINIC")).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "Tài chính & tiền thủ thuật" }),
    ).toBeTruthy();
    expect((screen.getByLabelText("Kỳ báo cáo") as HTMLInputElement).value).toBe("2026-09");
    expect(screen.getByRole("button", { name: "Làm mới" })).toBeTruthy();
  });

  it("falls_back_to_the_current_month_when_the_address_has_none", () => {
    nav.search = "";
    renderShell(ACCOUNTANT, "manager");

    expect(screen.getByTestId("probe").textContent).toMatch(/^\d{4}-\d{2}\|clinic\|true\|0$/);
  });

  it("puts_the_chosen_month_in_the_address", () => {
    renderShell(ACCOUNTANT, "manager");

    fireEvent.change(screen.getByLabelText("Kỳ báo cáo"), { target: { value: "2026-08" } });

    expect(nav.replace).toHaveBeenCalledWith("/finance?month=2026-08");
  });

  it("ignores_a_month_that_is_not_one", () => {
    renderShell(ACCOUNTANT, "manager");

    fireEvent.change(screen.getByLabelText("Kỳ báo cáo"), { target: { value: "" } });

    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("makes_the_pages_load_again_when_refresh_is_pressed", async () => {
    const user = userEvent.setup();
    renderShell(ACCOUNTANT, "manager");

    await user.click(screen.getByRole("button", { name: "Làm mới" }));

    expect(screen.getByTestId("probe").textContent).toBe("2026-09|clinic|true|1");
  });
});

describe("the tabs of each role", () => {
  it("gives_the_accountant_the_four_old_tabs_then_the_close_and_the_export", () => {
    renderShell(ACCOUNTANT, "manager");

    expect(tabNames()).toEqual([
      "Tổng quan",
      "Tiền thủ thuật",
      "Chính sách tỷ lệ",
      "Phiếu thu & thông báo",
      "Chốt kỳ",
      "Xuất CSV",
    ]);
  });

  it("gives_a_doctor_the_overview_the_table_and_the_export_and_no_scope_switch", () => {
    renderShell(DOCTOR, "doctor");

    expect(tabNames()).toEqual(["Tổng quan", "Tiền thủ thuật", "Xuất CSV"]);
    expect(screen.queryByRole("button", { name: "Toàn phòng khám" })).toBeNull();
    expect(screen.getByTestId("probe").textContent).toBe("2026-09|own|false|0");
  });

  it("keeps_the_month_in_every_tab_link_and_marks_the_current_one", () => {
    nav.pathname = "/finance/entries";
    renderShell(ACCOUNTANT, "manager");

    const links = within(
      screen.getByRole("navigation", { name: "Phân hệ tài chính" }),
    ).getAllByRole("link");

    expect(links[2]?.getAttribute("href")).toBe("/finance/rates?month=2026-09");
    expect(links[1]?.getAttribute("aria-current")).toBe("page");
    expect(links[0]?.getAttribute("aria-current")).toBeNull();
  });

  it("does_not_let_a_doctor_ask_for_the_clinic_scope", () => {
    nav.search = "month=2026-09&scope=clinic";
    renderShell(DOCTOR, "doctor");

    expect(screen.getByTestId("probe").textContent).toBe("2026-09|own|false|0");
  });
});

describe("the owner", () => {
  it("flips_between_the_clinic_and_the_personal_view_with_the_scope_in_the_address", async () => {
    const user = userEvent.setup();
    renderShell(OWNER, "owner");

    expect(
      screen.getByRole("button", { name: "Toàn phòng khám" }).getAttribute("aria-pressed"),
    ).toBe("true");
    await user.click(screen.getByRole("button", { name: "Cá nhân" }));

    expect(nav.replace).toHaveBeenCalledWith("/finance?month=2026-09&scope=own");
  });

  it("shows_three_tabs_and_no_writing_on_the_personal_view", () => {
    nav.search = "month=2026-09&scope=own";
    renderShell(OWNER, "owner");

    expect(tabNames()).toEqual(["Tổng quan", "Tiền thủ thuật", "Xuất CSV"]);
    expect(screen.getByTestId("probe").textContent).toBe("2026-09|own|false|0");
    expect(
      within(screen.getByRole("navigation", { name: "Phân hệ tài chính" }))
        .getAllByRole("link")[0]
        ?.getAttribute("href"),
    ).toBe("/finance?month=2026-09&scope=own");
  });

  it("drops_the_scope_from_the_address_when_it_goes_back_to_the_clinic", async () => {
    const user = userEvent.setup();
    nav.search = "month=2026-09&scope=own";
    renderShell(OWNER, "owner");

    await user.click(screen.getByRole("button", { name: "Toàn phòng khám" }));

    expect(nav.replace).toHaveBeenCalledWith("/finance?month=2026-09");
  });
});

describe("a role without finance access", () => {
  it("is_told_so_and_gets_no_tab_and_no_page", () => {
    renderShell(["order.read"], "manager");

    expect(screen.getByText("Vai trò của bạn không xem được dữ liệu tài chính.")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Phân hệ tài chính" })).toBeNull();
    expect(screen.queryByTestId("probe")).toBeNull();
  });
});
