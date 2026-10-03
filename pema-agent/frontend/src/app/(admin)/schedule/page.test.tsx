// @vitest-environment jsdom
// "Điều phối lịch" against a fake of the typed client: what it asks the board for, what it offers per status and
// role, and what a click sends. The BE rules (hours, double booking) are the BE's: a refusal is shown as it comes.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";
import { SessionProvider } from "@/lib/session/session-context";

import SchedulePage from "./page";

type ScheduleItem = Schemas["ScheduleItem"];

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));

// The typed client is the unmanaged dependency (the network); the page is exercised through it.
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

function visit(over: Partial<ScheduleItem>): ScheduleItem {
  return {
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
    version: 3,
    ...over,
  };
}

function board(items: ScheduleItem[], view: "day" | "week" = "day"): Schemas["ScheduleOut"] {
  return {
    view,
    from_day: "2026-09-20",
    to_day: view === "week" ? "2026-09-26" : "2026-09-20",
    doctor_id: null,
    items,
    doctors: DOCTORS,
  };
}

const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) });

function answerWith(items: ScheduleItem[]) {
  api.get.mockImplementation((path: string, init?: { params?: { query?: { view?: string } } }) => {
    if (path === "/api/v1/appointments/schedule") {
      return ok(board(items, init?.params?.query?.view === "week" ? "week" : "day"));
    }
    return ok({ items: [], total: 0, limit: 200, offset: 0 });
  });
}

function renderPage(role: Schemas["Role"], permissions: Permission[]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Võ Ngọc Trâm",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <SchedulePage />
      </ToastProvider>
    </SessionProvider>,
  );
}

const RECEPTION: Permission[] = [
  "appointment.read",
  "appointment.write",
  "appointment.check_in",
  "patient.read",
];

function boardRequests(): { query: { day?: string; view?: string; doctor_id?: string } }[] {
  return api.get.mock.calls
    .filter((call) => call[0] === "/api/v1/appointments/schedule")
    .map((call) => (call[1] as { params: { query: { day?: string } } }).params);
}

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

describe("schedule page", () => {
  describe("given a day with one visit in each reception status", () => {
    const rows = [
      visit({ id: "a-1", status: "booked", starts_at: "2026-09-20T08:00:00+07:00" }),
      visit({
        id: "a-2",
        status: "confirmed",
        patient_name: "Trần Minh Anh",
        starts_at: "2026-09-20T09:00:00+07:00",
      }),
      visit({
        id: "a-3",
        status: "arrived",
        patient_name: "Lê Hoàng Yến",
        starts_at: "2026-09-20T10:00:00+07:00",
      }),
      visit({
        id: "a-4",
        status: "in_progress",
        patient_name: "Phạm Gia Hân",
        starts_at: "2026-09-20T11:00:00+07:00",
      }),
      visit({
        id: "a-5",
        status: "completed",
        patient_name: "Võ Thị Lan",
        starts_at: "2026-09-20T14:00:00+07:00",
      }),
    ];

    it("asks_the_board_for_the_clinic_day_as_a_day_view", async () => {
      answerWith(rows);
      renderPage("reception", RECEPTION);

      await waitFor(() => expect(boardRequests().length).toBeGreaterThan(0));
      const query = boardRequests()[0]?.query;
      expect(query?.day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(query?.view).toBe("day");
    });

    it("shows_each_visit_with_the_old_status_words", async () => {
      answerWith(rows);
      renderPage("reception", RECEPTION);

      const cards = await screen.findAllByRole("article");
      const words = ["Đặt hẹn", "Đã xác nhận", "Đang chờ", "Đang điều trị", "Hoàn tất"];
      words.forEach((word, i) =>
        expect(within(cards[i] as HTMLElement).getByText(word)).toBeTruthy(),
      );
    });

    it("offers_the_next_step_of_each_visit_and_nothing_on_a_finished_one", async () => {
      answerWith(rows);
      renderPage("reception", RECEPTION);

      const cards = await screen.findAllByRole("article");
      const buttons = cards.map((card) =>
        within(card)
          .queryAllByRole("button")
          .map((b) => b.textContent)
          .filter(
            (text) => text !== null && ["Check-in", "Bắt đầu điều trị", "Hoàn tất"].includes(text),
          ),
      );
      expect(buttons).toEqual([["Check-in"], ["Check-in"], ["Bắt đầu điều trị"], ["Hoàn tất"], []]);
    });
  });

  describe("given a booked visit", () => {
    it("check_in_sends_the_version_the_person_saw_and_reloads_the_board", async () => {
      answerWith([visit({ status: "booked", version: 3 })]);
      api.post.mockImplementation(() => ok(visit({ status: "arrived", version: 4 })));
      renderPage("reception", RECEPTION);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Check-in" }));

      await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
      const [path, init] = api.post.mock.calls[0] as [
        string,
        { params: { path: { appointment_id: string } }; body: { version: number } },
      ];
      expect(path).toBe("/api/v1/appointments/{appointment_id}/check-in");
      expect(init.params.path.appointment_id).toBe("a-1");
      expect(init.body.version).toBe(3);
      await waitFor(() => expect(boardRequests().length).toBeGreaterThan(1));
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
      renderPage("reception", RECEPTION);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Check-in" }));

      expect(
        await screen.findByText("Trạng thái lịch hiện tại không cho phép thao tác này."),
      ).toBeTruthy();
    });
  });

  describe("given a role that may read but not change the schedule", () => {
    it("has_no_book_button_and_no_step_buttons", async () => {
      answerWith([visit({ status: "booked" })]);
      renderPage("cs_staff", ["appointment.read", "patient.read"]);

      await screen.findByRole("article");
      expect(screen.queryByRole("button", { name: /Đặt lịch/ })).toBeNull();
      expect(screen.queryByRole("button", { name: "Check-in" })).toBeNull();
    });
  });

  describe("given a doctor", () => {
    it("has_no_doctor_filter_because_the_board_is_their_own", async () => {
      answerWith([visit({})]);
      renderPage("doctor", [
        "appointment.read",
        "appointment.write",
        "appointment.check_in",
        "patient.read",
      ]);

      await screen.findByRole("article");
      expect(screen.queryByLabelText("Bác sĩ")).toBeNull();
      expect(boardRequests()[0]?.query.doctor_id).toBeUndefined();
    });
  });

  describe("given the week view", () => {
    it("asks_for_seven_days_and_lists_each_day", async () => {
      answerWith([visit({})]);
      renderPage("reception", RECEPTION);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "7 ngày" }));

      await waitFor(() => expect(boardRequests().some((r) => r.query.view === "week")).toBe(true));
      expect(await screen.findAllByRole("button", { name: /＋ Đặt lịch/ })).toHaveLength(8);
    });
  });

  describe("given a day without visits", () => {
    it("says_there_is_nothing_booked", async () => {
      answerWith([]);
      renderPage("reception", RECEPTION);

      expect(await screen.findByText("Chưa có lịch hẹn")).toBeTruthy();
    });
  });

  describe("given cancelled and missed visits", () => {
    it("hides_them_until_asked_for", async () => {
      answerWith([
        visit({ id: "a-1", status: "booked" }),
        visit({ id: "a-2", status: "cancelled", cancel_reason: "Bận" }),
        visit({ id: "a-3", status: "missed" }),
      ]);
      renderPage("reception", RECEPTION);
      const user = userEvent.setup();

      expect(await screen.findAllByRole("article")).toHaveLength(1);
      await user.click(screen.getByRole("button", { name: /Hiện lịch hủy/ }));

      expect(screen.getAllByRole("article")).toHaveLength(3);
    });
  });
});
