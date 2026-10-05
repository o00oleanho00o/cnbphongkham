// @vitest-environment jsdom
// The patient page of the accountant: no Patient 360, the billing tab from its own projection, and the buttons the
// old web keeps for that role (WC27) while the clinical ones stay away (WC25 for care). The typed client is faked.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FinanceOnlyView } from "@/components/ops/patient/finance-only-view";
import { PATIENT_ID, asRole, ok, plan } from "@/components/ops/patient/test-support";
import type { Permission } from "@/lib/session/session-context";

const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});

const ACCOUNTANT: Permission[] = [
  "patient.read",
  "finance.read",
  "finance.write",
  "finance.collect",
  "order.read",
  "order.write",
];

beforeEach(() => {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/patients/{patient_id}/finance-tab")
      return Promise.resolve(
        ok({
          patient: {
            id: PATIENT_ID,
            code: "P001",
            full_name: "Nguyễn Thu Hà",
            gender: "female",
            version: 1,
          },
          plans: [plan({ agreed_price_vnd: 9_500_000 })],
        }),
      );
    if (path === "/api/v1/finance/invoices") return Promise.resolve(ok({ items: [], total: 0 }));
    return Promise.resolve(ok({ items: [], total: 0 }));
  });
});

afterEach(() => cleanup());

describe("FinanceOnlyView", () => {
  it("the_accountant_sees_the_header_the_courses_and_keeps_the_billing_buttons", async () => {
    render(asRole(ACCOUNTANT, <FinanceOnlyView patientId={PATIENT_ID} />));

    expect(await screen.findByRole("heading", { name: "Nguyễn Thu Hà" })).not.toBeNull();
    expect(screen.getByText(/9\.500\.000\s?₫ sau giảm/)).not.toBeNull();
    expect(screen.getByRole("button", { name: "＋ Thêm dịch vụ" })).not.toBeNull();
    expect(screen.getAllByRole("link", { name: "Mở thu ngân →" }).length).toBeGreaterThan(0);
  });

  it("no_clinical_route_is_called", async () => {
    render(asRole(ACCOUNTANT, <FinanceOnlyView patientId={PATIENT_ID} />));
    await screen.findByRole("heading", { name: "Nguyễn Thu Hà" });

    const paths = api.get.mock.calls.map((call) => String(call[0]));

    expect(
      paths.filter((path) => /\/360|clinical|brief|sessions|consult|media/.test(path)),
    ).toEqual([]);
  });
});
