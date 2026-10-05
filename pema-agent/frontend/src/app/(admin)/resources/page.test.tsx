// @vitest-environment jsdom
// The doctors-and-rooms screen (`/resources`) against a fake of the typed client: the doctor card (shift of the day,
// the break between its intervals, the load of the day, the link to the doctor's schedule), the rooms, the blocks
// ("Khóa phòng", "Gỡ khóa") and what each role sees. The rules (08:00-18:00, who may change) are the backend's
// (`backend/apps/api/tests/clinic/test_catalog_resources.py`).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import ResourcesPage from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real.
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
      DELETE: (...args: unknown[]) => api.del(...args),
    },
  };
});

const SHIFT = [
  { start: "08:00", end: "12:00" },
  { start: "13:00", end: "18:00" },
];

const TAM: Schemas["DoctorResourceOut"] = {
  user_id: "doc-tam",
  name: "BS. Lê Minh Tâm",
  active: true,
  has_shift: true,
  shift: SHIFT,
  shift_minutes: 540,
  booked_count: 6,
  booked_minutes: 270,
};
const AN: Schemas["DoctorResourceOut"] = {
  user_id: "doc-an",
  name: "BS. Trương Hoài An",
  active: true,
  has_shift: false,
  shift: [],
  shift_minutes: 0,
  booked_count: 0,
  booked_minutes: 0,
};
const ROOM: Schemas["RoomOut"] = {
  id: "room-laser",
  name: "Laser & thủ thuật",
  capacity: 1,
  active: true,
  version: 1,
};
const BLOCK: Schemas["RoomBlockOut"] = {
  id: "block-1",
  room_id: ROOM.id,
  day: "2026-09-21",
  start: "14:00",
  end: "15:00",
  reason: "Bảo trì thiết bị laser",
  created_by: null,
};

const MANAGER: Permission[] = ["appointment.read", "admin.rules", "care.admin"];
const RECEPTION: Permission[] = ["appointment.read"];

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function refused(status: number, code: string, message: string) {
  return Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
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
        <ResourcesPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

beforeEach(() => {
  api.get
    .mockReset()
    .mockImplementation(() =>
      ok({ day: "2026-09-20", doctors: [TAM, AN], rooms: [ROOM], blocks: [BLOCK] }),
    );
  api.post.mockReset().mockImplementation(() => ok(BLOCK));
  api.patch.mockReset().mockImplementation(() => ok(ROOM));
  api.del
    .mockReset()
    .mockImplementation(() => Promise.resolve({ response: new Response(null, { status: 204 }) }));
});

afterEach(() => cleanup());

describe("doctor cards", () => {
  it("shows_the_shift_the_break_the_load_and_the_link_to_the_schedule", async () => {
    renderPage(MANAGER);

    expect(await screen.findByRole("heading", { name: "BS. Lê Minh Tâm" })).toBeTruthy();
    expect(screen.getByText("08:00–12:00 · 13:00–18:00")).toBeTruthy();
    expect(screen.getByText("Nghỉ 12:00–13:00")).toBeTruthy();
    expect(screen.getByText("6 lịch · 270 phút điều trị / 540 phút ca")).toBeTruthy();
    expect(
      screen
        .getByRole("progressbar", { name: "Tải lịch của BS. Lê Minh Tâm" })
        .getAttribute("aria-valuenow"),
    ).toBe("50");
    expect(
      screen.getByRole("link", { name: "Xem lịch bác sĩ BS. Lê Minh Tâm" }).getAttribute("href"),
    ).toBe("/schedule?doctor=doc-tam");
  });

  it("tells_a_doctor_without_a_shift_where_to_set_one", async () => {
    renderPage(MANAGER);

    expect(await screen.findByText(/Chưa thiết lập ca làm việc/)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Thiết lập ở Kỹ năng và ca trực" }).getAttribute("href"),
    ).toBe("/admin/care/staff");
  });

  it("asks_for_the_chosen_day", async () => {
    renderPage(MANAGER);
    await screen.findByRole("heading", { name: "BS. Lê Minh Tâm" });

    const date = screen.getByLabelText("Ngày xem tải lịch");
    fireEvent.change(date, { target: { value: "2026-10-05" } });

    await waitFor(() => {
      const last = api.get.mock.calls.at(-1)?.[1] as { params: { query: { day: string } } };
      expect(last.params.query.day).toBe("2026-10-05");
    });
  });
});

describe("blocks", () => {
  it("lists_the_blocks_with_their_room_time_and_reason", async () => {
    renderPage(MANAGER);

    const row = (await screen.findByText("Bảo trì thiết bị laser")).closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Laser & thủ thuật")).toBeTruthy();
    expect(within(row as HTMLElement).getByText("14:00–15:00")).toBeTruthy();
  });

  it("refuses_a_window_that_ends_before_it_starts_without_calling_the_backend", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Khóa phòng" }));

    await user.type(screen.getByLabelText(/Lý do/), "Vệ sinh");
    await user.clear(screen.getByLabelText("Đến"));
    await user.type(screen.getByLabelText("Đến"), "13:00");
    await user.click(screen.getAllByRole("button", { name: "Khóa phòng" }).at(-1) as HTMLElement);

    expect(
      await screen.findByText("Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do."),
    ).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("sends_a_valid_block_with_its_room_day_window_and_reason", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Khóa phòng" }));

    await user.type(screen.getByLabelText(/Lý do/), "  Vệ sinh phòng ");
    await user.click(screen.getAllByRole("button", { name: "Khóa phòng" }).at(-1) as HTMLElement);

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const options = api.post.mock.calls[0]?.[1] as { body: Record<string, unknown> };
    expect(options.body).toEqual({
      room_id: ROOM.id,
      day: "2026-09-20",
      start: "14:00",
      end: "15:00",
      reason: "Vệ sinh phòng",
    });
  });

  it("removes_a_block_only_after_the_confirmation", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);

    await user.click(
      await screen.findByRole("button", { name: "Gỡ khóa Laser & thủ thuật 14:00" }),
    );
    expect(api.del).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Gỡ khóa" }));

    await waitFor(() => expect(api.del).toHaveBeenCalledTimes(1));
    const options = api.del.mock.calls[0]?.[1] as { params: { path: { block_id: string } } };
    expect(options.params.path.block_id).toBe("block-1");
  });

  it("keeps_the_block_when_the_confirmation_is_declined", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);

    await user.click(
      await screen.findByRole("button", { name: "Gỡ khóa Laser & thủ thuật 14:00" }),
    );
    await user.click(screen.getByRole("button", { name: "Hủy" }));

    expect(api.del).not.toHaveBeenCalled();
  });
});

describe("rooms", () => {
  it("renames_a_room_with_the_version_that_was_read", async () => {
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Sửa phòng Laser & thủ thuật" }));

    const name = screen.getByLabelText(/Tên phòng/);
    await user.clear(name);
    await user.type(name, "Laser 1");
    await user.click(screen.getByRole("button", { name: "Lưu phòng" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const options = api.patch.mock.calls[0]?.[1] as { body: Record<string, unknown> };
    expect(options.body).toMatchObject({ version: 1, name: "Laser 1", capacity: 1, active: true });
  });

  it("shows_the_backend_sentence_when_the_name_is_taken", async () => {
    api.patch.mockImplementation(() => refused(422, "validation_failed", "Tên phòng đã tồn tại."));
    const user = userEvent.setup();
    renderPage(MANAGER);
    await user.click(await screen.findByRole("button", { name: "Sửa phòng Laser & thủ thuật" }));

    await user.click(screen.getByRole("button", { name: "Lưu phòng" }));

    expect(await screen.findByText("Tên phòng đã tồn tại.")).toBeTruthy();
  });
});

describe("a role that only reads", () => {
  it("sees_cards_and_blocks_but_no_button_that_changes_them", async () => {
    renderPage(RECEPTION);

    expect(await screen.findByRole("heading", { name: "BS. Lê Minh Tâm" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Khóa phòng" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Thêm phòng" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Gỡ khóa/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "Thiết lập ở Kỹ năng và ca trực" })).toBeNull();
    expect(
      screen.getByText(/Chỉ chủ phòng khám và quản lý được thêm hoặc gỡ khóa phòng/),
    ).toBeTruthy();
  });
});
