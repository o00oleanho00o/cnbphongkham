// @vitest-environment jsdom
// Patient 360 with five tabs: who sees which, how the tab is kept in the address, and that the overview still
// carries everything the screen showed before the tabs.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Patient360View } from "@/components/ops/patient/patient-360-view";
import { PATIENT_ID, asRole, ok, plan } from "@/components/ops/patient/test-support";
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  replace: vi.fn(),
  search: { current: "" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: api.replace }),
  usePathname: () => `/patients/${PATIENT_ID}`,
  useSearchParams: () => new URLSearchParams(api.search.current),
}));
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
    },
  };
});

const DATA = {
  patient: {
    id: PATIENT_ID,
    code: "P001",
    full_name: "Nguyễn Thu Hà",
    gender: "female",
    doctor_name: "BS. Lê Minh Tâm",
    marketing_opt_out: false,
    version: 1,
  },
  profile: { lifecycle_stage: "treating", marketing_opt_out: false, risk_level: "normal" },
  plans: [plan()],
  consents: [],
} as unknown as Schemas["Patient360"];

const DOCTOR: Permission[] = [
  "patient.read_360",
  "session.read",
  "session.write",
  "media.read",
  "media.write",
  "care.read",
];
const MANAGER: Permission[] = ["patient.read_360"];

function renderView(permissions: Permission[]) {
  return render(asRole(permissions, <Patient360View data={DATA} onChanged={() => undefined} />));
}

/** The full label of each tab (the phone label sits in a sibling span that is hidden from `lg`). */
const tabNames = (): string[] =>
  screen
    .getAllByRole("tab")
    .map((tab) => tab.querySelector("span.hidden")?.textContent ?? tab.textContent ?? "");

beforeEach(() => {
  api.search.current = "";
  api.replace.mockReset();
  api.get.mockReset().mockResolvedValue(ok([]));
  api.post.mockReset().mockResolvedValue(ok({}));
  api.patch.mockReset().mockResolvedValue(ok({}));
});

afterEach(() => cleanup());

describe("Patient360View", () => {
  it("a_doctor_sees_the_six_tabs_of_the_old_web", () => {
    renderView(DOCTOR);

    expect(tabNames()).toEqual([
      "Tổng quan",
      "Tư vấn",
      "Kế hoạch",
      "Buổi điều trị",
      "Ảnh trước / sau",
      "Dịch vụ & tài chính",
    ]);
  });

  it("a_manager_sees_the_overview_the_plan_and_the_services_and_finance_tab", () => {
    renderView(MANAGER);

    expect(tabNames()).toEqual(["Tổng quan", "Kế hoạch", "Dịch vụ & tài chính"]);
  });

  it("the_overview_opens_first_and_carries_the_information_cards", () => {
    renderView(DOCTOR);

    const titles = [
      "Thông tin",
      "Chăm sóc sau điều trị",
      "Lịch hẹn",
      "Đồng ý của khách",
      "Dòng thời gian",
    ];

    expect(titles.map((title) => screen.queryByRole("heading", { name: title }) !== null)).toEqual(
      titles.map(() => true),
    );
  });

  it("choosing_a_tab_puts_it_in_the_address_without_scrolling", async () => {
    renderView(DOCTOR);

    await userEvent.setup().click(screen.getByRole("tab", { name: /Tư vấn/ }));

    expect(api.replace).toHaveBeenCalledWith(`/patients/${PATIENT_ID}?tab=consult`, {
      scroll: false,
    });
  });

  it("choosing_the_overview_clears_the_tab_from_the_address", async () => {
    api.search.current = "tab=plan";
    renderView(DOCTOR);

    await userEvent.setup().click(screen.getByRole("tab", { name: /Tổng quan/ }));

    expect(api.replace).toHaveBeenCalledWith(`/patients/${PATIENT_ID}`, { scroll: false });
  });

  it("the_tab_named_in_the_address_is_the_one_that_opens", () => {
    api.search.current = "tab=plan";
    renderView(DOCTOR);

    expect(screen.getByRole("tab", { name: /Kế hoạch/ }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("a_tab_the_role_may_not_open_falls_back_to_the_overview", () => {
    api.search.current = "tab=photos";
    renderView(MANAGER);

    expect(screen.getByRole("tab", { name: /Tổng quan/ }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("only_someone_who_writes_sessions_gets_the_record_session_button_in_the_header", () => {
    renderView(MANAGER);

    expect(screen.queryByRole("button", { name: /Ghi buổi điều trị/ })).toBeNull();
  });

  it("the_header_button_opens_the_session_tab", async () => {
    renderView(DOCTOR);

    await userEvent.setup().click(screen.getByRole("button", { name: /Ghi buổi điều trị/ }));

    expect(api.replace).toHaveBeenCalledWith(`/patients/${PATIENT_ID}?tab=session`, {
      scroll: false,
    });
  });

  it("ai_brief_is_for_whoever_writes_sessions_and_the_message_button_for_whoever_may_reply", () => {
    renderView([...DOCTOR, "conversation.reply"]);

    expect(screen.getByRole("button", { name: /AI brief/ })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Nhắn tin" })).not.toBeNull();
  });

  it("a_manager_gets_neither_the_brief_nor_the_message_button", () => {
    renderView(MANAGER);

    expect(screen.queryByRole("button", { name: /AI brief/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Nhắn tin" })).toBeNull();
  });

  it("the_warning_lines_are_chips_in_the_header", () => {
    render(
      asRole(
        DOCTOR,
        <Patient360View
          data={{ ...DATA, alerts: ["Da nhạy cảm"] } as Schemas["Patient360"]}
          onChanged={() => undefined}
        />,
      ),
    );

    expect(
      within(screen.getByRole("list", { name: "Thông tin cần nhớ" })).getByText("⚠ Da nhạy cảm"),
    ).not.toBeNull();
  });
});
