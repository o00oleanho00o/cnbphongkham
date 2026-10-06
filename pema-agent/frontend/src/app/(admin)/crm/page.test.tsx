// @vitest-environment jsdom
// "Vòng đời khách hàng" against a fake of the typed client: the group cards show the numbers, the list of the open
// group shows who is overdue, the opt-out switch sends the audited patient update with the version it read (and only
// for someone who may write patients), and the other two tabs show the log and the rules.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider } from "@/lib/session/session-context";

import CrmPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));

// The HTTP client is the unmanaged dependency: a hand-written fake of the routes the page calls.
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

const ID = "00000000-0000-4000-8002-000000000002";

const SEGMENTS = {
  total_patients: 10,
  marketing_opt_out: 1,
  segments: [
    { key: "new", count: 0 },
    { key: "returning", count: 2 },
    { key: "treating", count: 3 },
    { key: "dormant", count: 2 },
    { key: "reactivated", count: 1 },
    { key: "at_risk", count: 2 },
  ],
};

const ROW = {
  patient_id: ID,
  patient_code: "P002",
  full_name: "Trần Minh Anh",
  version: 4,
  lifecycle_stage: "returning",
  last_visit_at: "2026-08-11",
  expected_next_visit_at: "2026-09-08",
  overdue_days: 12,
  remaining_sessions: 0,
  risk_level: "high",
  marketing_opt_out: false,
  cs_owner_name: "CSKH Mai Anh (mẫu)",
};

const ACTIVITY = {
  id: "a1",
  patient_id: ID,
  task_id: null,
  kind: "cskh",
  channel: "zalo",
  outcome: "unanswered",
  note: "Đã nhắn Zalo hỏi lịch tái khám.",
  actor_user_id: null,
  actor_name: "CSKH Mai Anh (mẫu)",
  occurred_at: "2026-09-18T09:00:00+07:00",
  next_action_at: null,
};

const RULE = {
  id: "r1",
  rule_key: "d1",
  name: "Sau thủ thuật · D+1",
  trigger: "Hoàn tất buổi",
  delay_days: 1,
  suggested_action: "Gọi hỏi tình trạng",
  priority: "high",
  active: true,
  send_mode: "staff_task",
  conditions: {},
  version: 1,
};

const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) });

function answer(path: string) {
  if (path === "/api/v1/crm/segments") return ok(SEGMENTS);
  if (path === "/api/v1/crm/segments/{segment}/patients") {
    return ok({ items: [ROW], total: 1, limit: 25, offset: 0 });
  }
  if (path === "/api/v1/crm/activities") {
    return ok({ items: [ACTIVITY], total: 1, limit: 50, offset: 0 });
  }
  if (path === "/api/v1/crm/rules") return ok([RULE]);
  if (path === "/api/v1/patients") return ok({ items: [], total: 0, limit: 200, offset: 0 });
  return Promise.reject(new Error(`unexpected ${path}`));
}

function renderCrm(permissions: Parameters<typeof SessionProvider>[0]["permissions"]) {
  return render(
    <SessionProvider
      user={{
        id: "00000000-0000-4000-8000-000000000004",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <CrmPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

beforeEach(() => {
  api.get.mockReset().mockImplementation((path: string) => answer(path));
  api.patch.mockReset().mockImplementation(() => ok({ ...ROW, marketing_opt_out: true }));
});

afterEach(cleanup);

describe("crm page: groups", () => {
  it("shows_a_card_with_the_count_of_each_group", async () => {
    renderCrm(["crm.task.read"]);
    const treating = await screen.findByRole("button", { name: /Đang điều trị/ });
    expect(within(treating).getByText("3")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Nguy cơ mất khách/ })).toBeTruthy();
    expect(screen.getByText(/1 khách từ chối quảng bá/)).toBeTruthy();
  });

  it("opens_on_the_first_stage_that_has_patients_and_lists_who_is_overdue", async () => {
    renderCrm(["crm.task.read"]);
    expect(await screen.findByText("Trần Minh Anh")).toBeTruthy();
    expect(screen.getByText("Quá hạn 12 ngày")).toBeTruthy();
    const call = api.get.mock.calls.find((c) => c[0] === "/api/v1/crm/segments/{segment}/patients");
    expect((call?.[1] as { params: { path: { segment: string } } }).params.path.segment).toBe(
      "returning",
    );
  });

  it("choosing_another_card_asks_for_that_group", async () => {
    renderCrm(["crm.task.read"]);
    await screen.findByText("Trần Minh Anh");
    await userEvent.click(screen.getByRole("button", { name: /Lâu chưa quay lại/ }));
    await waitFor(() => {
      const last = api.get.mock.calls.filter(
        (c) => c[0] === "/api/v1/crm/segments/{segment}/patients",
      );
      expect(
        (last.at(-1)?.[1] as { params: { path: { segment: string } } }).params.path.segment,
      ).toBe("dormant");
    });
  });

  it("without_patient_write_the_opt_out_state_is_shown_but_cannot_be_switched", async () => {
    renderCrm(["crm.task.read"]);
    await screen.findByText("Trần Minh Anh");
    expect(screen.getByText("Có thể chăm sóc")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ghi nhận từ chối" })).toBeNull();
  });

  it("switching_opt_out_asks_first_then_sends_the_version_it_read", async () => {
    renderCrm(["crm.task.read", "patient.write"]);
    await userEvent.click(await screen.findByRole("button", { name: "Ghi nhận từ chối" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ghi nhận từ chối" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    const [path, options] = api.patch.mock.calls[0] as [
      string,
      { params: { path: { patient_id: string } }; body: unknown },
    ];
    expect(path).toBe("/api/v1/patients/{patient_id}");
    expect(options.params.path.patient_id).toBe(ID);
    expect(options.body).toEqual({ version: 4, marketing_opt_out: true });
  });

  it("cancelling_the_question_changes_nothing", async () => {
    renderCrm(["crm.task.read", "patient.write"]);
    await userEvent.click(await screen.findByRole("button", { name: "Ghi nhận từ chối" }));
    await userEvent.click(await screen.findByRole("button", { name: "Hủy" }));
    expect(api.patch).not.toHaveBeenCalled();
  });
});

describe("crm page: log and rules", () => {
  it("the_log_shows_channel_outcome_and_who_logged_it", async () => {
    renderCrm(["crm.task.read"]);
    await userEvent.click(await screen.findByRole("tab", { name: "Nhật ký chăm sóc" }));
    expect(await screen.findByText("Đã nhắn Zalo hỏi lịch tái khám.")).toBeTruthy();
    expect(screen.getAllByText("Zalo").length).toBeGreaterThan(0);
    expect(screen.getByText("Không nghe máy")).toBeTruthy();
    expect(screen.getByText(/CSKH Mai Anh \(mẫu\)/)).toBeTruthy();
  });

  it("the_rules_are_shown_as_read_only_text", async () => {
    renderCrm(["crm.task.read"]);
    await userEvent.click(await screen.findByRole("tab", { name: "Quy tắc tự động" }));
    expect(await screen.findByText("Sau thủ thuật · D+1")).toBeTruthy();
    expect(screen.getByText("Gọi hỏi tình trạng")).toBeTruthy();
    expect(screen.getByText(/sau 1 ngày → tạo việc/)).toBeTruthy();
    expect(screen.getByText("Chỉ tạo việc cho nhân viên")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Lưu|Sửa/ })).toBeNull();
  });
});
