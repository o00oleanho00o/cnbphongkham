// @vitest-environment jsdom
// "Việc hôm nay" against a fake of the typed client. The real API takes `due_by` as a DATE: a datetime there is a
// 422 ("Dữ liệu gửi lên không hợp lệ") that only showed up against the real backend, never against the mock.
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider } from "@/lib/session/session-context";

import TodayPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));
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

function renderToday() {
  return render(
    <SessionProvider
      user={{
        id: "00000000-0000-4000-8000-000000000004",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={["crm.task.read", "crm.task.resolve"]}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <TodayPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  api.get.mockReset().mockImplementation(() =>
    Promise.resolve({
      data: { items: [], total: 0, limit: 200, offset: 0 },
      response: new Response(null, { status: 200 }),
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("today page request", () => {
  it("asks_for_tasks_due_by_a_calendar_date_not_a_datetime", async () => {
    renderToday();
    await waitFor(() => {
      expect(api.get.mock.calls.some((call) => call[0] === "/api/v1/crm/tasks")).toBe(true);
    });
    const call = api.get.mock.calls.find((c) => c[0] === "/api/v1/crm/tasks");
    const query = (call?.[1] as { params: { query: { due_by?: string } } }).params.query;
    expect(query.due_by).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
