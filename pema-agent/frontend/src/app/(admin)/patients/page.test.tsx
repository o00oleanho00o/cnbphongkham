// @vitest-environment jsdom
// /patients: the four chips of the old web ask the backend for their own page, and "＋ Hồ sơ mới" creates a record
// through the existing `POST /api/v1/patients` and opens it. The typed client is the network, faked here.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import PatientsPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), push: vi.fn() }));

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
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: api.push }),
}));

const ok = <T,>(data: T) => ({ data, response: new Response(null, { status: 200 }) });
const PAGE = {
  items: [{ id: "p-1", code: "P001", full_name: "Nguyễn Thu Hà", gender: "female", version: 1 }],
  total: 1,
  limit: 50,
  offset: 0,
};

function renderPage(permissions: Permission[]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Lễ tân Lan (mẫu)",
        role: "reception",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <PatientsPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

const lastQuery = (): Record<string, unknown> =>
  (api.get.mock.lastCall?.[1] as { params: { query: Record<string, unknown> } }).params.query;

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok(PAGE));
  api.post.mockReset().mockResolvedValue(ok({ ...PAGE.items[0], id: "p-new" }));
  api.push.mockReset();
});

afterEach(() => cleanup());

describe("PatientsPage", () => {
  it("lists_the_four_chips_of_the_old_web_with_all_selected", async () => {
    renderPage(["patient.read"]);
    await screen.findByText("Nguyễn Thu Hà");

    const chips = screen.getAllByRole("button", { pressed: false }).map((b) => b.textContent);

    expect(chips).toEqual(["Đang điều trị", "Tái khám tuần này", "Có cảnh báo"]);
    expect(screen.getByRole("button", { name: "Tất cả", pressed: true })).not.toBeNull();
  });

  it("choosing_a_chip_asks_the_backend_for_that_view", async () => {
    renderPage(["patient.read"]);
    await screen.findByText("Nguyễn Thu Hà");

    await userEvent.setup().click(screen.getByRole("button", { name: "Có cảnh báo" }));

    await waitFor(() => expect(lastQuery().view).toBe("alerts"));
  });

  it("the_new_record_button_is_only_for_someone_who_writes_patients", async () => {
    renderPage(["patient.read"]);
    await screen.findByText("Nguyễn Thu Hà");

    expect(screen.queryByRole("button", { name: "＋ Hồ sơ mới" })).toBeNull();
  });

  it("a_name_is_required_to_create_a_record", async () => {
    renderPage(["patient.read", "patient.write"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "＋ Hồ sơ mới" }));
    await user.click(screen.getByRole("button", { name: "Tạo hồ sơ" }));

    expect(screen.getByRole("alert").textContent).toBe("Nhập tên người bệnh");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("the_created_record_is_sent_and_opened", async () => {
    renderPage(["patient.read", "patient.write"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "＋ Hồ sơ mới" }));
    await user.type(screen.getByLabelText(/Họ và tên/), "Trần Bảo Châu");
    await user.click(screen.getByRole("button", { name: "Tạo hồ sơ" }));

    await waitFor(() => expect(api.push).toHaveBeenCalledWith("/patients/p-new"));
    expect((api.post.mock.calls[0]?.[1] as { body: unknown }).body).toEqual({
      full_name: "Trần Bảo Châu",
      gender: "unknown",
      birth_date: null,
      phone: null,
      source: null,
    });
  });
});
