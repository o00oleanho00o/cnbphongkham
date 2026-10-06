// @vitest-environment jsdom
// "Chính sách tỷ lệ" (`/finance/rates`) against a fake of the typed client: every service with its basis, its rate and
// its version of the terms, what is sent when a rate is saved (basis points, the version that was read), the sentence
// of the old web for a rate that cannot be, and the read-only line for a role that may not change the terms.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACCOUNTANT, DOCTOR, ok, refused, renderFinance } from "@/components/finance/test-support";
import type { Schemas } from "@/lib/api";

import FinanceRatesPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
    },
  };
});

function service(over: Partial<Schemas["ServiceOut"]> = {}): Schemas["ServiceOut"] {
  return {
    id: "svc-1",
    code: "follow-up-visit",
    name: "Tái khám & đánh giá",
    active: true,
    price_vnd: 300_000,
    rate_bp: 1000,
    basis: "net",
    duration_min: 30,
    buffer_min: 0,
    room_ids: [],
    terms_version: 1,
    version: 4,
    ...over,
  };
}

const SERVICES = [
  service(),
  service({
    id: "svc-2",
    name: "Laser theo chỉ định",
    rate_bp: 1250,
    basis: "list",
    terms_version: 3,
  }),
];

beforeEach(() => {
  api.get.mockReset().mockImplementation(() => ok(SERVICES));
  api.patch.mockReset().mockImplementation(() => ok(service()));
});

afterEach(() => cleanup());

describe("the policy of every service", () => {
  it("shows_the_version_the_basis_and_the_rate_of_each_service", async () => {
    renderFinance(<FinanceRatesPage />);

    expect(await screen.findByText("Chính sách theo thủ thuật")).toBeTruthy();
    expect(screen.getByText("Phiên bản 1")).toBeTruthy();
    expect(screen.getByText("Phiên bản 3")).toBeTruthy();
    const laser = screen.getByRole("form", { name: "Chính sách Laser theo chỉ định" });
    expect((within(laser).getByLabelText("Cơ sở") as HTMLSelectElement).value).toBe("list");
    expect((within(laser).getByLabelText(/^Tỷ lệ %/) as HTMLInputElement).value).toBe("12.5");
    expect(screen.getByText(/Áp dụng cho lượt tạo sau khi lưu\./)).toBeTruthy();
    expect(
      screen.getByText("Cơ sở tính có 3 lựa chọn: Giá sau giảm · Giá niêm yết · Theo thực thu."),
    ).toBeTruthy();
  });

  it("offers_the_three_bases_of_the_old_web", async () => {
    renderFinance(<FinanceRatesPage />);
    const form = await screen.findByRole("form", { name: "Chính sách Tái khám & đánh giá" });

    const options = within(within(form).getByLabelText("Cơ sở")).getAllByRole("option");

    expect(options.map((o) => o.textContent)).toEqual([
      "Giá sau giảm",
      "Giá niêm yết",
      "Theo thực thu",
    ]);
  });
});

describe("saving a rate", () => {
  it("sends_the_rate_in_basis_points_the_basis_and_the_version_that_was_read", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceRatesPage />);
    const form = await screen.findByRole("form", { name: "Chính sách Tái khám & đánh giá" });

    await user.selectOptions(within(form).getByLabelText("Cơ sở"), "collected");
    const rate = within(form).getByLabelText(/^Tỷ lệ %/);
    await user.clear(rate);
    await user.type(rate, "12.5");
    await user.click(within(form).getByRole("button", { name: "Lưu tỷ lệ" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const [path, options] = api.patch.mock.calls[0] as [string, { params: unknown; body: unknown }];
    expect(path).toBe("/api/v1/services/{service_id}");
    expect(options.params).toEqual({ path: { service_id: "svc-1" } });
    expect(options.body).toEqual({ version: 4, rate_bp: 1250, basis: "collected" });
  });

  it("says_nothing_was_changed_instead_of_making_a_new_version", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceRatesPage />);
    const form = await screen.findByRole("form", { name: "Chính sách Tái khám & đánh giá" });

    await user.click(within(form).getByRole("button", { name: "Lưu tỷ lệ" }));

    expect(await screen.findByText("Tỷ lệ chưa đổi.")).toBeTruthy();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("tells_a_rate_over_a_hundred_percent_in_place", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceRatesPage />);
    const form = await screen.findByRole("form", { name: "Chính sách Tái khám & đánh giá" });

    const rate = within(form).getByLabelText(/^Tỷ lệ %/);
    await user.clear(rate);
    await user.type(rate, "120");
    await user.click(within(form).getByRole("button", { name: "Lưu tỷ lệ" }));

    expect((await within(form).findByRole("alert")).textContent).toContain(
      "Tỷ lệ tiền thủ thuật từ 0 đến 100%",
    );
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("shows_the_sentence_of_the_backend_when_the_terms_changed_meanwhile", async () => {
    const user = userEvent.setup();
    api.patch.mockImplementation(() =>
      refused(
        409,
        "version_conflict",
        "Bản ghi đã được người khác thay đổi. Hãy tải lại rồi thử lại.",
      ),
    );
    renderFinance(<FinanceRatesPage />);
    const form = await screen.findByRole("form", { name: "Chính sách Tái khám & đánh giá" });

    await user.selectOptions(within(form).getByLabelText("Cơ sở"), "list");
    await user.click(within(form).getByRole("button", { name: "Lưu tỷ lệ" }));

    expect((await within(form).findByRole("alert")).textContent).toContain("Hãy tải lại");
  });
});

describe("a role that may not change the terms", () => {
  it("sees_the_services_but_no_form_when_the_rate_is_hidden_from_it", async () => {
    api.get.mockImplementation(() => ok([service({ rate_bp: null, basis: null })]));
    renderFinance(<FinanceRatesPage />, {
      permissions: ACCOUNTANT.filter((p) => p !== "admin.rules"),
    });

    expect(await screen.findByText("Tái khám & đánh giá")).toBeTruthy();
    expect(screen.getByText("Tỷ lệ chỉ hiển thị cho người quản lý danh mục.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Lưu tỷ lệ" })).toBeNull();
  });

  it("shows_no_form_to_a_doctor_even_if_the_page_were_opened", async () => {
    renderFinance(<FinanceRatesPage />, { permissions: DOCTOR, role: "doctor" });

    expect(await screen.findByText("Phiên bản 1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Lưu tỷ lệ" })).toBeNull();
  });
});
