// @vitest-environment jsdom
// The "Dịch vụ & tài chính" tab: which cards and buttons each kind of caller gets, the empty states of the old web
// (WC29), and what "＋ Thêm dịch vụ" sends. The typed client is the network, the one dependency faked here.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FinanceTab } from "@/components/ops/patient/finance-tab";
import { PATIENT_ID, asRole, ok, plan } from "@/components/ops/patient/test-support";
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
    },
  };
});

const priced = plan({
  unit_price_vnd: 2_500_000,
  discount_vnd: 500_000,
  agreed_price_vnd: 9_500_000,
  service_terms_version: 1,
});

function card(plans: Schemas["TreatmentPlanOut"][]): Schemas["Patient360"] {
  return {
    patient: { id: PATIENT_ID, code: "P001", full_name: "Nguyễn Thu Hà", version: 1 },
    profile: { lifecycle_stage: "treating", marketing_opt_out: false, risk_level: "normal" },
    plans,
  } as unknown as Schemas["Patient360"];
}

const SERVICES = [
  {
    id: "svc-1",
    code: "laser-co2",
    name: "Laser theo chỉ định",
    price_vnd: 2_500_000,
    active: true,
  },
];
const INVOICE = {
  id: "inv-1",
  number: "HD-0001",
  invoice_date: "2026-09-06",
  source: "finance",
  amount_vnd: 1_200_000,
  received_vnd: 1_200_000,
  due_vnd: 0,
};

function route(path: string) {
  if (path === "/api/v1/finance/invoices") return ok({ items: [INVOICE], total: 1 });
  if (path === "/api/v1/services") return ok(SERVICES);
  if (path === "/api/v1/orders") return ok({ items: [], total: 0 });
  return ok([]);
}

function renderTab(permissions: Permission[], plans = [priced]) {
  return render(asRole(permissions, <FinanceTab data={card(plans)} onChanged={() => undefined} />));
}

beforeEach(() => {
  api.get.mockReset().mockImplementation((path: string) => Promise.resolve(route(path)));
  api.post.mockReset().mockResolvedValue(ok({}));
});

afterEach(() => cleanup());

describe("FinanceTab", () => {
  it("the_owner_sees_invoices_courses_with_the_fixed_price_and_the_buttons", async () => {
    renderTab(["finance.read", "finance.collect", "finance.write", "order.read", "order.write"]);

    expect(await screen.findByText("HD-0001")).not.toBeNull();
    expect(screen.getByText("Hóa đơn của Nguyễn Thu Hà")).not.toBeNull();
    expect(screen.getByText(/9\.500\.000\s?₫ sau giảm/)).not.toBeNull();
    expect(screen.getByRole("button", { name: "＋ Thêm dịch vụ" })).not.toBeNull();
    expect(screen.getAllByRole("link", { name: "Mở thu ngân →" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "＋ Tạo đơn nháp" })).not.toBeNull();
    expect(screen.getByText("Chưa có đơn thuốc.")).not.toBeNull();
  });

  it("care_staff_see_the_sessions_and_no_money_and_no_billing_buttons", () => {
    renderTab([], [plan()]);

    expect(screen.getByText("2/4 buổi")).not.toBeNull();
    expect(screen.queryByText(/Hóa đơn của/)).toBeNull();
    expect(screen.queryByText(/sau giảm/)).toBeNull();
    expect(screen.queryByRole("button", { name: "＋ Thêm dịch vụ" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Mở thu ngân →" })).toBeNull();
    expect(screen.queryByRole("link", { name: "＋ Tạo đơn nháp" })).toBeNull();
  });

  it("a_patient_without_a_course_gets_the_empty_sentence", () => {
    renderTab([], []);

    expect(screen.getByText("Chưa có dịch vụ gắn với hồ sơ.")).not.toBeNull();
  });

  it("the_billing_role_without_clinical_rights_has_no_draft_button", async () => {
    renderTab(["finance.read", "finance.collect", "finance.write", "order.read"]);

    await screen.findByText("HD-0001");

    expect(screen.queryByRole("link", { name: "＋ Tạo đơn nháp" })).toBeNull();
  });

  it("adding_a_service_sends_the_service_the_sessions_and_the_discount", async () => {
    renderTab(["finance.read", "finance.write"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "＋ Thêm dịch vụ" }));
    await screen.findByText("Thêm dịch vụ vào liệu trình");
    const sessions = screen.getByLabelText("Số buổi");
    await user.clear(sessions);
    await user.type(sessions, "5");
    await user.clear(screen.getByLabelText("Giảm giá (₫)"));
    await user.type(screen.getByLabelText("Giảm giá (₫)"), "500000");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect((api.post.mock.calls[0]?.[1] as { body: unknown }).body).toEqual({
      service_id: "svc-1",
      sessions: 5,
      discount_vnd: 500000,
    });
  });

  it("more_than_twenty_sessions_is_told_in_place", async () => {
    renderTab(["finance.write"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "＋ Thêm dịch vụ" }));
    await screen.findByText("Thêm dịch vụ vào liệu trình");
    const sessions = screen.getByLabelText("Số buổi");
    await user.clear(sessions);
    await user.type(sessions, "21");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    expect(screen.getByRole("alert").textContent).toBe("Số buổi từ 1 đến 20.");
    expect(api.post).not.toHaveBeenCalled();
  });
});
