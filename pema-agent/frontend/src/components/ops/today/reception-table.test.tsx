// @vitest-environment jsdom
// The reception table of "/today" (old "Hôm nay tại Pema") against a fake of the typed client: the rows and the
// buttons each status offers, what a click sends (the same transitions as the board), the tiles that filter, the
// search, the 25-row pages and what a role without check-in sees. The rules are the BE's.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { clinicDateKey } from "@/lib/ops/format";
import type { PatientIndex } from "@/lib/ops/use-patient-names";
import type { Permission } from "@/lib/session/session-context";
import { SessionProvider } from "@/lib/session/session-context";

import { ReceptionTable } from "./reception-table";

type ScheduleItem = Schemas["ScheduleItem"];

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
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

class FakeEventSource {
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close(): void {
    this.readyState = 2;
  }
}

const DOCTORS = [
  { id: "d-an", name: "BS. Trương Hoài An" },
  { id: "d-tam", name: "BS. Lê Minh Tâm" },
];

const PATIENTS: PatientIndex = new Map(
  ["p-1", "p-2"].map((id, i) => [
    id,
    {
      id,
      code: `P00${i + 1}`,
      full_name: i === 0 ? "Nguyễn Thu Hà" : "Trần Minh Anh",
      gender: "female",
      marketing_opt_out: false,
      version: 1,
      phone: i === 0 ? "0900 000 101" : "0900 000 102",
      birth_date: "1994-01-01",
    } satisfies Schemas["PatientOut"],
  ]),
);

function visit(over: Partial<ScheduleItem>): ScheduleItem {
  return {
    id: "a-1",
    patient_id: "p-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "d-an",
    doctor_name: "BS. Trương Hoài An",
    room_id: "r-1",
    room_name: "Khám da liễu",
    created_by_name: "Lê Thị Lan",
    starts_at: `${clinicDateKey()}T09:00:00+07:00`,
    duration_min: 30,
    status: "booked",
    note: "Tái khám",
    version: 3,
    ...over,
  };
}

const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) });

function answerWith(items: ScheduleItem[]) {
  api.get.mockImplementation((path: string) => {
    if (path === "/api/v1/appointments/schedule") {
      return ok({
        view: "day",
        from_day: clinicDateKey(),
        to_day: clinicDateKey(),
        doctor_id: null,
        items,
        doctors: DOCTORS,
        rooms: [],
        blocks: [],
      } satisfies Schemas["ScheduleOut"]);
    }
    return ok({ items: [], total: 0, limit: 200, offset: 0 });
  });
}

const RECEPTION: Permission[] = [
  "appointment.read",
  "appointment.write",
  "appointment.check_in",
  "patient.read",
  "patient.read_360",
];

function renderTable(role: Schemas["Role"], permissions: Permission[]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Lê Thị Lan",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <ReceptionTable patients={PATIENTS} />
      </ToastProvider>
    </SessionProvider>,
  );
}

const table = async () => within(await screen.findByRole("table"));

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("reception table", () => {
  it("asks_for_the_clinic_day_and_draws_the_old_columns", async () => {
    answerWith([visit({})]);
    renderTable("reception", RECEPTION);

    const rows = await table();
    [
      "Giờ",
      "Mã KH · bệnh nhân",
      "Liên hệ",
      "Nội dung",
      "Trạng thái",
      "Bác sĩ",
      "Phòng",
      "Người tạo",
      "Tiếp đón",
    ].forEach((name) => expect(rows.getByRole("columnheader", { name })).toBeTruthy());
    const query = (
      api.get.mock.calls.find((c) => c[0] === "/api/v1/appointments/schedule")?.[1] as {
        params: { query: { day: string; view: string } };
      }
    ).params.query;
    expect(query.day).toBe(clinicDateKey());
    expect(query.view).toBe("day");
  });

  it("shows_name_code_phone_age_note_doctor_room_and_creator_of_a_visit", async () => {
    answerWith([visit({})]);
    renderTable("reception", RECEPTION);

    const rows = await table();
    expect(rows.getByRole("link", { name: "Nguyễn Thu Hà" }).getAttribute("href")).toBe(
      "/patients/p-1",
    );
    expect(rows.getByText("P001")).toBeTruthy();
    expect(rows.getByText("0900 000 101")).toBeTruthy();
    expect(rows.getByText(/tuổi$/)).toBeTruthy();
    expect(rows.getByText("Tái khám")).toBeTruthy();
    expect(rows.getByText("Chưa đến")).toBeTruthy();
    expect(rows.getByText("BS. Trương Hoài An")).toBeTruthy();
    expect(rows.getByText("Khám da liễu")).toBeTruthy();
    expect(rows.getByText("Lê Thị Lan")).toBeTruthy();
  });

  it("offers_check_in_and_absent_then_invite_in_then_open_360_by_status", async () => {
    answerWith([
      visit({ id: "a-1", status: "booked", starts_at: `${clinicDateKey()}T08:00:00+07:00` }),
      visit({ id: "a-2", status: "arrived", starts_at: `${clinicDateKey()}T09:00:00+07:00` }),
      visit({ id: "a-3", status: "completed", starts_at: `${clinicDateKey()}T10:00:00+07:00` }),
    ]);
    renderTable("reception", RECEPTION);

    const rows = await table();
    const body = rows.getAllByRole("row").slice(1);
    const buttons = body.map((row) =>
      within(row)
        .queryAllByRole("button")
        .map((b) => b.textContent),
    );
    expect(buttons[0]).toEqual(["Check-in", "Vắng"]);
    expect(buttons[1]).toEqual(["Mời vào phòng"]);
    expect(buttons[2]).toEqual([]);
    expect(within(body[2] as HTMLElement).getByRole("link", { name: "Mở 360" })).toBeTruthy();
  });

  it("check_in_sends_the_version_the_person_saw_and_reloads", async () => {
    answerWith([visit({ status: "booked", version: 3 })]);
    api.post.mockImplementation(() => ok(visit({ status: "arrived", version: 4 })));
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();

    await user.click((await table()).getByRole("button", { name: "Check-in" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, init] = api.post.mock.calls[0] as [
      string,
      { params: { path: { appointment_id: string } }; body: { version: number } },
    ];
    expect(path).toBe("/api/v1/appointments/{appointment_id}/check-in");
    expect(init.params.path.appointment_id).toBe("a-1");
    expect(init.body.version).toBe(3);
    await waitFor(() =>
      expect(
        api.get.mock.calls.filter((c) => c[0] === "/api/v1/appointments/schedule").length,
      ).toBe(2),
    );
  });

  it("absent_and_invite_in_call_the_miss_and_start_transitions", async () => {
    answerWith([
      visit({ id: "a-1", status: "booked", starts_at: `${clinicDateKey()}T08:00:00+07:00` }),
      visit({ id: "a-2", status: "arrived", starts_at: `${clinicDateKey()}T09:00:00+07:00` }),
    ]);
    api.post.mockImplementation(() => ok(visit({})));
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Vắng" }));
    await user.click(await screen.findByRole("button", { name: "Mời vào phòng" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls.map((c) => c[0])).toEqual([
      "/api/v1/appointments/{appointment_id}/miss",
      "/api/v1/appointments/{appointment_id}/start",
    ]);
  });

  it("a_refusal_of_the_backend_is_shown_in_its_own_words", async () => {
    answerWith([visit({ status: "booked" })]);
    api.post.mockImplementation(() =>
      Promise.resolve({
        error: {
          error: {
            code: "invalid_state",
            message: "Trạng thái lịch hiện tại không cho phép thao tác này.",
          },
        },
        response: new Response(null, { status: 409 }),
      }),
    );
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();

    await user.click((await table()).getByRole("button", { name: "Check-in" }));

    expect(
      await screen.findByText("Trạng thái lịch hiện tại không cho phép thao tác này."),
    ).toBeTruthy();
  });

  it("a_role_without_check_in_sees_no_step_buttons", async () => {
    answerWith([visit({ status: "booked" })]);
    renderTable("cs_staff", ["appointment.read", "patient.read"]);

    const rows = await table();
    expect(rows.queryByRole("button", { name: "Check-in" })).toBeNull();
    expect(rows.queryByRole("button", { name: "Vắng" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Đặt lịch mới/ })).toBeNull();
  });

  it("counts_the_day_in_tiles_and_a_tile_filters_the_rows", async () => {
    answerWith([
      visit({ id: "a-1", status: "booked", starts_at: `${clinicDateKey()}T08:00:00+07:00` }),
      visit({ id: "a-2", status: "confirmed", starts_at: `${clinicDateKey()}T08:30:00+07:00` }),
      visit({ id: "a-3", status: "arrived", starts_at: `${clinicDateKey()}T09:00:00+07:00` }),
      visit({ id: "a-4", status: "missed", starts_at: `${clinicDateKey()}T10:00:00+07:00` }),
    ]);
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();

    const stats = await screen.findByLabelText("Thống kê tiếp đón");
    expect(within(stats).getByText("Tổng lịch").previousSibling?.textContent).toBe("4");
    expect(within(stats).getByText("Đã đến").previousSibling?.textContent).toBe("1");
    expect(within(stats).getByText("Chưa đến").previousSibling?.textContent).toBe("2");

    await user.click(within(stats).getByRole("button", { name: /Đang chờ/ }));

    expect((await table()).getAllByRole("row").slice(1)).toHaveLength(1);
    expect((screen.getByLabelText("Trạng thái") as HTMLSelectElement).value).toBe("arrived");
  });

  it("searches_by_name_and_says_when_nothing_matches", async () => {
    answerWith([
      visit({ id: "a-1" }),
      visit({ id: "a-2", patient_id: "p-2", patient_code: "P002", patient_name: "Trần Minh Anh" }),
    ]);
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();
    await table();

    await user.type(screen.getByLabelText("Tên / mã KH / liên hệ"), "minh anh");
    expect((await table()).getAllByRole("row").slice(1)).toHaveLength(1);

    await user.clear(screen.getByLabelText("Tên / mã KH / liên hệ"));
    await user.type(screen.getByLabelText("Tên / mã KH / liên hệ"), "không có ai");
    expect(await screen.findByText("Không có lịch phù hợp.")).toBeTruthy();
  });

  it("pages_by_25_rows", async () => {
    answerWith(
      Array.from({ length: 31 }, (_, i) =>
        visit({
          id: `a-${i}`,
          starts_at: `${clinicDateKey()}T${String(8 + Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}:00+07:00`,
        }),
      ),
    );
    renderTable("reception", RECEPTION);
    const user = userEvent.setup();

    expect(await screen.findByText("31 lịch · Trang 1/2 · 25 dòng/trang")).toBeTruthy();
    expect((await table()).getAllByRole("row").slice(1)).toHaveLength(25);

    await user.click(screen.getByRole("button", { name: "Sau →" }));

    expect(await screen.findByText("31 lịch · Trang 2/2 · 25 dòng/trang")).toBeTruthy();
    expect((await table()).getAllByRole("row").slice(1)).toHaveLength(6);
  });

  it("a_doctor_has_no_doctor_filter_because_the_day_is_their_own", async () => {
    answerWith([visit({})]);
    renderTable("doctor", RECEPTION);

    await table();
    expect(screen.queryByLabelText("Bác sĩ")).toBeNull();
  });
});
