// @vitest-environment jsdom
// The booking and detail sheet against a fake of the typed client: what a booking sends, what "Tìm giờ trống" fills
// in, what a cancellation needs, and that a refusal of the BE is shown in its own words.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";
import { SessionProvider } from "@/lib/session/session-context";

import { AppointmentSheet, type SheetTarget } from "./appointment-sheet";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));

// The typed client is the unmanaged dependency (the network); the sheet is exercised through it.
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

const DOCTORS = [
  { id: "d-an", name: "BS. Trương Hoài An" },
  { id: "u-doctor", name: "BS. Lê Minh Tâm" },
];

const PATIENTS = new Map<string, Schemas["PatientOut"]>([
  [
    "p-1",
    {
      id: "p-1",
      code: "P001",
      full_name: "Nguyễn Thu Hà",
      gender: "female",
      birth_date: null,
      doctor_id: null,
      cs_owner_id: null,
      phone: null,
      source: null,
      marketing_opt_out: false,
      version: 1,
    },
  ],
]);

const BOOKED: Schemas["ScheduleItem"] = {
  id: "a-1",
  patient_id: "p-1",
  patient_code: "P001",
  patient_name: "Nguyễn Thu Hà",
  doctor_id: "d-an",
  doctor_name: "BS. Trương Hoài An",
  starts_at: "2026-09-20T09:00:00+07:00",
  duration_min: 30,
  status: "booked",
  note: "Tái khám",
  version: 2,
};

const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) });
const refused = (status: number, code: string, message: string) =>
  Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });

const RECEPTION: Permission[] = [
  "appointment.read",
  "appointment.write",
  "appointment.check_in",
  "patient.read",
];

function renderSheet(
  target: SheetTarget,
  options: { role?: Schemas["Role"]; permissions?: Permission[] } = {},
) {
  const saved = vi.fn();
  render(
    <SessionProvider
      user={{
        id: "u-doctor",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Võ Ngọc Trâm",
        role: options.role ?? "reception",
      }}
      permissions={options.permissions ?? RECEPTION}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <AppointmentSheet
          target={target}
          doctors={DOCTORS}
          patients={PATIENTS}
          onClose={() => undefined}
          onSaved={saved}
        />
      </ToastProvider>
    </SessionProvider>,
  );
  return { saved };
}

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.patch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("appointment sheet", () => {
  describe("given a new booking for a day", () => {
    const create: SheetTarget = { kind: "create", day: "2026-09-21", doctorId: null };

    it("sends_the_patient_the_doctor_and_the_start_in_clinic_time", async () => {
      api.post.mockImplementation(() => ok({ ...BOOKED }));
      const { saved } = renderSheet(create);
      const user = userEvent.setup();

      await user.selectOptions(screen.getByLabelText(/Bệnh nhân/), "p-1");
      await user.selectOptions(screen.getByLabelText("Bác sĩ"), "d-an");
      await user.click(screen.getByRole("button", { name: "Xác nhận đặt lịch" }));

      await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
      const [path, init] = api.post.mock.calls[0] as [string, { body: Record<string, unknown> }];
      expect(path).toBe("/api/v1/appointments");
      expect(init.body).toMatchObject({
        patient_id: "p-1",
        doctor_id: "d-an",
        starts_at: "2026-09-21T09:00:00+07:00",
        duration_min: 30,
      });
    });

    it("asks_for_a_patient_before_it_sends_anything", async () => {
      renderSheet(create);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: "Xác nhận đặt lịch" }));

      expect(await screen.findByText("Hãy chọn bệnh nhân.")).toBeTruthy();
      expect(api.post).not.toHaveBeenCalled();
    });

    it("shows_the_backend_sentence_for_a_double_booking_and_stays_open", async () => {
      api.post.mockImplementation(() =>
        refused(409, "appointment_conflict", "Trùng lịch của bác sĩ lúc 21/09 09:00."),
      );
      const { saved } = renderSheet(create);
      const user = userEvent.setup();

      await user.selectOptions(screen.getByLabelText(/Bệnh nhân/), "p-1");
      await user.click(screen.getByRole("button", { name: "Xác nhận đặt lịch" }));

      expect(await screen.findByText("Trùng lịch của bác sĩ lúc 21/09 09:00.")).toBeTruthy();
      expect(saved).not.toHaveBeenCalled();
    });

    it("find_a_free_slot_fills_the_time_with_the_first_free_start", async () => {
      api.get.mockImplementation(() => ok({ starts_at: "2026-09-21T08:30:00+07:00" }));
      renderSheet(create);
      const user = userEvent.setup();

      await user.selectOptions(screen.getByLabelText(/Bệnh nhân/), "p-1");
      await user.click(screen.getByRole("button", { name: "Tìm giờ trống" }));

      await waitFor(() =>
        expect((screen.getByLabelText(/^Giờ/) as HTMLInputElement).value).toBe("08:30"),
      );
      expect(screen.getByText("Đã chọn giờ trống. Bấm xác nhận để lưu.")).toBeTruthy();
    });

    it("find_a_free_slot_says_so_when_the_day_has_none", async () => {
      api.get.mockImplementation(() => ok({ starts_at: null }));
      renderSheet(create);
      const user = userEvent.setup();

      await user.selectOptions(screen.getByLabelText(/Bệnh nhân/), "p-1");
      await user.click(screen.getByRole("button", { name: "Tìm giờ trống" }));

      expect(
        await screen.findByText("Không có giờ trống cho lựa chọn này. Hãy đổi ngày hoặc bác sĩ."),
      ).toBeTruthy();
    });
  });

  describe("given a doctor booking", () => {
    it("lists_only_themselves_as_the_doctor", () => {
      renderSheet(
        { kind: "create", day: "2026-09-21", doctorId: null },
        { role: "doctor", permissions: RECEPTION },
      );

      const options = [...(screen.getByLabelText("Bác sĩ") as HTMLSelectElement).options].map(
        (o) => o.textContent,
      );
      expect(options).toEqual(["BS. Lê Minh Tâm"]);
    });
  });

  describe("given a doctor who books", () => {
    it("books_for_themselves_without_choosing_a_doctor", async () => {
      api.post.mockImplementation(() => ok({ ...BOOKED }));
      const { saved } = renderSheet(
        { kind: "create", day: "2026-09-21", doctorId: null },
        { role: "doctor", permissions: RECEPTION },
      );
      const user = userEvent.setup();

      await user.selectOptions(screen.getByLabelText(/Bệnh nhân/), "p-1");
      await user.click(screen.getByRole("button", { name: "Xác nhận đặt lịch" }));

      await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
      const init = (api.post.mock.calls[0] as [string, { body: { doctor_id: string } }])[1];
      expect(init.body.doctor_id).toBe("u-doctor");
    });
  });

  describe("given a booked visit", () => {
    const edit: SheetTarget = { kind: "edit", item: BOOKED };

    it("offers_confirm_check_in_and_miss_and_a_cancel_section", () => {
      renderSheet(edit);

      ["Xác nhận lịch", "Check-in", "Vắng hẹn", "Hủy lịch"].forEach((name) =>
        expect(screen.getByRole("button", { name })).toBeTruthy(),
      );
    });

    it("confirm_sends_the_version_and_tells_the_page_to_reload", async () => {
      api.post.mockImplementation(() => ok({ ...BOOKED, status: "confirmed", version: 3 }));
      const { saved } = renderSheet(edit);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: "Xác nhận lịch" }));

      await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
      const [path, init] = api.post.mock.calls[0] as [string, { body: { version: number } }];
      expect(path).toBe("/api/v1/appointments/{appointment_id}/confirm");
      expect(init.body.version).toBe(2);
    });

    it("cancel_needs_a_reason_and_sends_it", async () => {
      api.post.mockImplementation(() => ok({ ...BOOKED, status: "cancelled" }));
      const { saved } = renderSheet(edit);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: "Hủy lịch" }));
      expect(await screen.findByText("Cần lý do hủy cho lịch đang hoạt động.")).toBeTruthy();
      expect(api.post).not.toHaveBeenCalled();

      await user.type(screen.getByLabelText("Lý do hủy"), "Bệnh nhân bận");
      await user.click(screen.getByRole("button", { name: "Hủy lịch" }));

      await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
      const init = (api.post.mock.calls[0] as [string, { body: { reason: string } }])[1];
      expect(init.body.reason).toBe("Bệnh nhân bận");
    });

    it("a_stale_version_asks_for_a_reload", async () => {
      api.post.mockImplementation(() => refused(409, "version_conflict", "Bản ghi đã đổi."));
      renderSheet(edit);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: "Check-in" }));

      expect(
        await screen.findByText(
          "Lịch này vừa được người khác thay đổi. Đóng hộp thoại để tải lại.",
        ),
      ).toBeTruthy();
    });

    it("saves_only_the_fields_that_changed", async () => {
      api.patch.mockImplementation(() => ok({ ...BOOKED }));
      const { saved } = renderSheet(edit);
      const user = userEvent.setup();

      await user.clear(screen.getByLabelText("Ghi chú"));
      await user.type(screen.getByLabelText("Ghi chú"), "Đổi ghi chú");
      await user.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

      await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
      const init = (api.patch.mock.calls[0] as [string, { body: Record<string, unknown> }])[1];
      expect(init.body).toEqual({ version: 2, note: "Đổi ghi chú" });
    });
  });

  describe("given a visit that already started", () => {
    it("is_read_only_and_offers_only_the_next_step", () => {
      renderSheet({ kind: "edit", item: { ...BOOKED, status: "in_progress" } });

      expect(screen.getByRole("button", { name: "Hoàn tất" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Lưu thay đổi" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Tìm giờ trống" })).toBeNull();
      expect((screen.getByLabelText("Ghi chú") as HTMLInputElement).disabled).toBe(true);
    });
  });
});
