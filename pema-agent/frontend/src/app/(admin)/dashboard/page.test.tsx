// @vitest-environment jsdom
// "Tổng quan" against a fake of the typed client: it shows what the BE computed, leaves out what the BE did not
// send, and never invents a number (no revenue; a rate with nothing to divide by is a dash).
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";
import { SessionProvider } from "@/lib/session/session-context";

import DashboardPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn() }));

// The typed client is the unmanaged dependency (the network); the page is exercised through it.
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});

class FakeEventSource {
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close(): void {
    this.readyState = 2;
  }
}

const APPOINTMENTS: Schemas["AppointmentKpis"] = {
  total: 8,
  upcoming: 3,
  waiting: 1,
  in_progress: 1,
  completed: 1,
  missed: 1,
  cancelled: 1,
  visits: 3,
};

function kpis(over: Partial<Schemas["DashboardKpisOut"]> = {}): Schemas["DashboardKpisOut"] {
  return {
    range: "today",
    scope: "clinic",
    starts_on: "2026-09-20",
    ends_on: "2026-09-20",
    appointments: APPOINTMENTS,
    patients: { seen: 3, new: 1, returning: 2 },
    care: {
      tasks_due: 4,
      tasks_resolved: 1,
      followup_completion_pct: 25,
      overdue_tasks: 2,
      overdue_patients: 2,
      contact_attempts: 0,
      contacts_reached: 0,
      contact_rate_pct: null,
      booked_after_care: 0,
    },
    ...over,
  };
}

function answerWith(body: Schemas["DashboardKpisOut"]) {
  api.get.mockImplementation(() =>
    Promise.resolve({ data: body, response: new Response(null, { status: 200 }) }),
  );
}

function renderPage(role: Schemas["Role"], permissions: Permission[]) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Nguyễn Thanh Hà",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <DashboardPage />
    </SessionProvider>,
  );
}

const OWNER: Permission[] = ["appointment.read", "crm.task.read", "patient.read"];

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  api.get.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The metric tile titled `label` (a status badge of the breakdown may carry the same words). */
function tile(label: string): HTMLElement {
  const holder = screen
    .getAllByText(label)
    .map((el) => el.closest<HTMLElement>("div.rounded-card"))
    .find((el) => el !== null);
  if (!holder) throw new Error(`no tile ${label}`);
  return holder;
}

describe("dashboard page", () => {
  describe("given the numbers of a clinic day", () => {
    it("asks_for_today_first_and_shows_the_appointment_tiles", async () => {
      answerWith(kpis());
      renderPage("owner", OWNER);

      expect(await screen.findByText("Lịch trong kỳ")).toBeTruthy();
      expect(api.get.mock.calls[0]?.[0]).toBe("/api/v1/dashboard/kpis");
      expect(
        (api.get.mock.calls[0]?.[1] as { params: { query: { range: string } } }).params.query.range,
      ).toBe("today");
      expect(within(tile("Lịch trong kỳ")).getByText("8")).toBeTruthy();
      expect(within(tile("Lịch trong kỳ")).getByText("3 chưa đến")).toBeTruthy();
      expect(within(tile("Vắng hẹn")).getByText("1 lịch đã hủy")).toBeTruthy();
      expect(within(tile("Bệnh nhân đã khám")).getByText("1 mới · 2 quay lại")).toBeTruthy();
    });

    it("shows_the_care_tiles_with_a_dash_for_a_rate_without_a_denominator", async () => {
      answerWith(kpis());
      renderPage("owner", OWNER);

      await screen.findByText("Việc đến hạn");
      expect(within(tile("Hoàn tất chăm sóc")).getByText("25%")).toBeTruthy();
      expect(within(tile("Liên hệ thành công")).getByText("–")).toBeTruthy();
      expect(within(tile("Việc quá hạn")).getByText("2 khách cần hỗ trợ")).toBeTruthy();
    });

    it("lists_every_status_with_its_count", async () => {
      answerWith(kpis());
      renderPage("owner", OWNER);

      const list = within(await screen.findByRole("list"));
      expect(list.getAllByRole("listitem")).toHaveLength(6);
      expect(list.getByText("Chưa đến")).toBeTruthy();
      expect(list.getByText("Đang chờ")).toBeTruthy();
      expect(list.getByText("Vắng hẹn")).toBeTruthy();
    });

    it("has_no_revenue_tile_and_says_why", async () => {
      answerWith(kpis());
      renderPage("owner", OWNER);

      await screen.findByText("Lịch trong kỳ");
      expect(screen.queryByText(/Phát sinh hôm nay/)).toBeNull();
      expect(screen.getByText(/Chưa có số doanh thu/)).toBeTruthy();
    });
  });

  describe("given a different range", () => {
    it("asks_again_with_the_week", async () => {
      answerWith(kpis());
      renderPage("owner", OWNER);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Tuần này" }));

      await waitFor(() => {
        const ranges = api.get.mock.calls.map(
          (c) => (c[1] as { params: { query: { range: string } } }).params.query.range,
        );
        expect(ranges).toContain("week");
      });
    });
  });

  describe("given a reception desk without care numbers", () => {
    it("shows_the_appointment_block_and_no_care_block", async () => {
      answerWith(kpis({ care: null }));
      renderPage("reception", ["appointment.read", "patient.read"]);

      await screen.findByText("Lịch trong kỳ");
      expect(screen.queryByText("Chăm sóc khách hàng")).toBeNull();
    });
  });

  describe("given a doctor", () => {
    it("is_told_the_numbers_are_their_own", async () => {
      answerWith(kpis({ scope: "doctor" }));
      renderPage("doctor", ["appointment.read", "crm.task.read"]);

      expect(await screen.findByText(/Chỉ gồm lịch của bạn/)).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Không gian bác sĩ" })).toBeTruthy();
    });
  });

  describe("given a failing backend", () => {
    it("shows_the_error_with_a_retry", async () => {
      api.get.mockImplementation(() =>
        Promise.resolve({
          error: { error: { code: "internal_error", message: "Lỗi hệ thống." } },
          response: new Response(null, { status: 500 }),
        }),
      );
      renderPage("owner", OWNER);

      expect(await screen.findByText("Lỗi hệ thống.")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Thử lại" })).toBeTruthy();
    });
  });
});
