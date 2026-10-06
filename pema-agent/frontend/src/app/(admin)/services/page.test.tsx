// @vitest-environment jsdom
// The service catalog screen (`/services`) against a fake of the typed client: what each role SEES (the manager has
// every button and the commission terms, a doctor only reads and never sees a rate), the edit form that sends only
// what changed and says when a price change starts a new version, the old web's sentence for a bad duration, the
// reload after a conflict, and the protocol list. The versioning itself is the backend's
// (`backend/apps/api/tests/clinic/test_catalog_services.py`).
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import ServicesPage from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real.
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));

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

const ROOM_A = "room-a";
const ROOM_B = "room-b";

const LASER: Schemas["ServiceOut"] = {
  id: "svc-laser",
  code: "laser-co2",
  name: "Laser theo chỉ định",
  active: true,
  protocol_code: "laser-co2",
  room_ids: [ROOM_B],
  price_vnd: 2_500_000,
  rate_bp: 2000,
  basis: "net",
  duration_min: 45,
  buffer_min: 15,
  terms_version: 1,
  version: 4,
};
const CONSULT: Schemas["ServiceOut"] = {
  ...LASER,
  id: "svc-consult",
  code: "dermatology-consult",
  name: "Tư vấn da liễu",
  protocol_code: null,
  room_ids: [ROOM_A],
  price_vnd: 500_000,
  rate_bp: 1500,
  duration_min: 30,
  buffer_min: 0,
  version: 1,
};
const PROTOCOL: Schemas["ProtocolOut"] = {
  id: "proto-laser",
  code: "laser-co2",
  name: "Laser CO2",
  milestones: [
    { rule_key: "d1", day: 1 },
    { rule_key: "d3", day: 3 },
    { rule_key: "d7", day: 7 },
  ],
  followup_days: 30,
  window_days: 45,
  active: true,
  version: 1,
};
const ROOMS: Schemas["RoomOut"][] = [
  { id: ROOM_A, name: "Khám da liễu", capacity: 1, active: true, version: 1 },
  { id: ROOM_B, name: "Laser & thủ thuật", capacity: 1, active: true, version: 1 },
];

const MANAGER: Permission[] = ["appointment.read", "admin.rules"];
const DOCTOR: Permission[] = ["appointment.read", "session.write"];

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function refused(status: number, code: string, message: string) {
  return Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });
}

function answers(services: Schemas["ServiceOut"][] = [LASER, CONSULT]) {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/services") return ok(services);
    if (path === "/api/v1/protocols") return ok([PROTOCOL]);
    if (path === "/api/v1/resources") {
      return ok({ day: "2026-09-20", doctors: [], rooms: ROOMS, blocks: [] });
    }
    return refused(404, "not_found", "?");
  });
}

function renderPage(permissions: Permission[]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Phạm Quốc Việt",
        role: "manager",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <ServicesPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

function patchBody(): Record<string, unknown> {
  const options = api.patch.mock.calls[0]?.[1] as { body: Record<string, unknown> };
  return options.body;
}

beforeEach(() => {
  answers();
  api.post.mockReset().mockImplementation(() => ok(CONSULT));
  api.patch.mockReset().mockImplementation(() => ok(LASER));
});

afterEach(() => cleanup());

describe("what a manager sees", () => {
  it("lists_each_service_with_price_time_rooms_and_the_commission_terms", async () => {
    renderPage(MANAGER);

    expect(await screen.findByRole("heading", { name: "Laser theo chỉ định" })).toBeTruthy();
    expect(screen.getByText(/2\.500\.000/)).toBeTruthy();
    expect(screen.getByText("45 phút điều trị")).toBeTruthy();
    expect(screen.getByText("15 phút chuẩn bị phòng")).toBeTruthy();
    expect(screen.getByText(/Tiền thủ thuật 20% · Giá sau giảm/)).toBeTruthy();
    expect(screen.getByText(/Phòng: Laser & thủ thuật/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thêm dịch vụ" })).toBeTruthy();
  });

  it("lists_the_protocol_with_its_milestones_and_review_day", async () => {
    renderPage(MANAGER);

    expect(await screen.findByText("Giao thức theo dõi sau thủ thuật")).toBeTruthy();
    expect(screen.getByText(/Mốc: D\+1, D\+3, D\+7/)).toBeTruthy();
    expect(screen.getByText(/đánh giá lại sau 30 ngày/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sửa giao thức Laser CO2" })).toBeTruthy();
  });
});

describe("what a doctor sees", () => {
  it("reads_the_catalog_without_edit_buttons_and_without_any_rate", async () => {
    answers([
      { ...LASER, rate_bp: null, basis: null },
      { ...CONSULT, rate_bp: null, basis: null },
    ]);
    renderPage(DOCTOR);

    expect(await screen.findByRole("heading", { name: "Tư vấn da liễu" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Chỉnh dịch vụ/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Thêm dịch vụ" })).toBeNull();
    expect(screen.queryByText(/Tiền thủ thuật/)).toBeNull();
    expect(
      screen.getByText(/Sửa giá và điều khoản là quyền của chủ phòng khám và quản lý/),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Sửa giao thức/ })).toBeNull();
  });
});

describe("editing a service", () => {
  it("sends_only_the_changed_field_with_the_version_that_was_read", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );

    const price = screen.getByLabelText("Giá (VND)");
    await user.clear(price);
    await user.type(price, "2600000");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(patchBody()).toEqual({ version: 4, price_vnd: 2_600_000 });
  });

  it("says_a_price_change_starts_the_next_terms_version_before_saving", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );

    expect(screen.queryByText(/Thay đổi này tạo phiên bản điều khoản/)).toBeNull();
    await user.type(screen.getByLabelText("Giá (VND)"), "0");

    expect(screen.getByText(/Thay đổi này tạo phiên bản điều khoản 2/)).toBeTruthy();
  });

  it("renaming_alone_starts_no_new_version", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );

    await user.type(screen.getByLabelText(/Tên dịch vụ/), " mới");

    expect(screen.queryByText(/Thay đổi này tạo phiên bản điều khoản/)).toBeNull();
  });

  it("tells_the_old_webs_sentence_for_a_bad_duration_and_sends_nothing", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );

    const minutes = screen.getByLabelText("Điều trị (phút)");
    await user.clear(minutes);
    await user.type(minutes, "10");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    expect(
      await screen.findByText(
        "Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.",
      ),
    ).toBeTruthy();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("sends_nothing_when_nothing_changed", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );

    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    expect(await screen.findByText("Không có thay đổi nào để lưu.")).toBeTruthy();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("explains_a_conflict_and_reloads_the_list", async () => {
    api.patch.mockImplementation(() => refused(409, "version_conflict", "x"));
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(
      await screen.findByRole("button", { name: "Chỉnh dịch vụ Laser theo chỉ định" }),
    );
    const loadsBefore = api.get.mock.calls.filter((c) => c[0] === "/api/v1/services").length;

    await user.type(screen.getByLabelText("Giá (VND)"), "1");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    expect(await screen.findByText(/vừa được người khác thay đổi/)).toBeTruthy();
    await waitFor(() =>
      expect(api.get.mock.calls.filter((c) => c[0] === "/api/v1/services").length).toBeGreaterThan(
        loadsBefore,
      ),
    );
  });
});

describe("adding a service", () => {
  it("refuses_a_code_with_capital_letters_before_calling_the_backend", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Thêm dịch vụ" }));

    await user.type(screen.getByLabelText(/Mã dịch vụ/), "Peel Light");
    await user.type(screen.getByLabelText(/Tên dịch vụ/), "Peel nhẹ");
    await user.type(screen.getByLabelText("Giá (VND)"), "700000");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    expect(await screen.findByText(/Mã dịch vụ không hợp lệ/)).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("creates_the_service_with_the_first_terms", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Thêm dịch vụ" }));

    await user.type(screen.getByLabelText(/Mã dịch vụ/), "peel-light");
    await user.type(screen.getByLabelText(/Tên dịch vụ/), "Peel nhẹ");
    await user.type(screen.getByLabelText("Giá (VND)"), "700000");
    await user.click(screen.getByRole("button", { name: "Lưu dịch vụ" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const options = api.post.mock.calls[0]?.[1] as { body: Record<string, unknown> };
    expect(options.body).toMatchObject({
      code: "peel-light",
      name: "Peel nhẹ",
      price_vnd: 700_000,
      rate_bp: 0,
      basis: "net",
      duration_min: 45,
      buffer_min: 15,
      protocol_code: null,
      room_ids: [],
    });
  });
});

describe("history", () => {
  it("opens_the_snapshots_of_a_service_newest_first", async () => {
    const history = [
      {
        version_no: 2,
        price_vnd: 2_600_000,
        rate_bp: 2000,
        basis: "net",
        duration_min: 45,
        buffer_min: 15,
        changed_by: null,
        created_at: "2026-09-20T09:00:00+07:00",
      },
      {
        version_no: 1,
        price_vnd: 2_500_000,
        rate_bp: 2000,
        basis: "net",
        duration_min: 45,
        buffer_min: 15,
        changed_by: null,
        created_at: "2026-08-01T09:00:00+07:00",
      },
    ];
    api.get.mockImplementation((path: string) => {
      if (path === "/api/v1/services/{service_id}")
        return ok({ ...LASER, terms_version: 2, history });
      if (path === "/api/v1/services") return ok([LASER]);
      if (path === "/api/v1/protocols") return ok([PROTOCOL]);
      return ok({ day: "2026-09-20", doctors: [], rooms: ROOMS, blocks: [] });
    });
    const user = userEvent.setup();
    renderPage(MANAGER);

    await user.click(
      await screen.findByRole("button", { name: "Lịch sử giá Laser theo chỉ định" }),
    );

    expect(await screen.findByText("Phiên bản 2")).toBeTruthy();
    expect(screen.getByText("Phiên bản 1")).toBeTruthy();
    expect(screen.getByText("Đang áp dụng")).toBeTruthy();
  });
});
