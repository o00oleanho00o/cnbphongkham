// @vitest-environment jsdom
// The "Phụ trách" box of the contact form in "Việc hôm nay": it keeps "Tôi" and "Giữ nguyên", and lists the other
// staff from `GET /api/v1/staff/assignable` (every signed-in member may read it). The chosen person is what the
// resolve call sends as `owner_user_id`. The rules themselves (who may take a task over) are the backend's.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResolveTaskSheet } from "@/components/ops/today/resolve-task-sheet";
import { ToastProvider } from "@/components/ops/toast";
import { ApiError } from "@/lib/api/client";
import type { Schemas } from "@/lib/api";
import type { AssignableStaff } from "@/lib/staff/assignable-staff";
import { SessionProvider } from "@/lib/session/session-context";

const api = vi.hoisted(() => ({ post: vi.fn(), staff: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { POST: (...args: unknown[]) => api.post(...args) } };
});
vi.mock("@/lib/staff/assignable-staff", () => ({
  fetchAssignableStaff: () => api.staff(),
  invalidateAssignableStaff: () => undefined,
}));

const ME = "00000000-0000-4000-8000-000000000004";
const LAN = "00000000-0000-4000-8000-000000000007";
const TAM = "00000000-0000-4000-8000-000000000003";
const HA = "00000000-0000-4000-8000-000000000001";

const STAFF: AssignableStaff[] = [
  { id: HA, name: "Nguyễn Thanh Hà", role: "owner" },
  { id: TAM, name: "BS. Lê Minh Tâm", role: "doctor" },
  { id: ME, name: "Mai Anh", role: "cs_staff" },
  { id: LAN, name: "Bùi Ngọc Lan", role: "manager" },
];

function task(overrides: Partial<Schemas["CrmTaskOut"]> = {}): Schemas["CrmTaskOut"] {
  return {
    id: "task-1",
    patient_id: "p-1",
    patient_code: "BN-0001",
    rule_key: "post_treatment_check",
    reason: "Hỏi thăm sau điều trị",
    suggested_action: "Gọi hỏi thăm",
    task_key: "k-1",
    priority: "normal",
    status: "open",
    due_at: "2026-10-02T09:00:00+07:00",
    created_at: "2026-10-01T09:00:00+07:00",
    version: 3,
    owner_user_id: null,
    owner_name: null,
    ...overrides,
  } as Schemas["CrmTaskOut"];
}

function renderSheet(t: Schemas["CrmTaskOut"]) {
  return render(
    <SessionProvider
      user={{
        id: ME,
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={["crm.task.resolve"]}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <ResolveTaskSheet
          task={t}
          patientName="Khách mẫu"
          presetFromShortcut={false}
          onClose={() => undefined}
          onDone={() => undefined}
        />
      </ToastProvider>
    </SessionProvider>,
  );
}

async function openOwnerBox() {
  const user = userEvent.setup();
  await user.click(screen.getByLabelText("Phụ trách"));
  return user;
}

function optionTexts(): string[] {
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
}

async function fillAndSave(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText("Kết quả"));
  await user.click(screen.getByRole("option", { name: "Đã liên hệ, chưa có nhu cầu" }));
  await user.type(
    screen.getByLabelText("Nội dung / kết quả trao đổi"),
    "Khách ổn, hẹn tái khám sau",
  );
  await user.click(screen.getByRole("button", { name: "Lưu kết quả chăm sóc" }));
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  api.staff.mockReset().mockResolvedValue(STAFF);
  api.post.mockReset().mockResolvedValue({
    data: task({ status: "resolved" }),
    response: new Response(null, { status: 200 }),
  });
});

afterEach(() => cleanup());

describe("ResolveTaskSheet owner box", () => {
  it("offers Tôi, Giữ nguyên with the current owner, then the other staff with their role", async () => {
    renderSheet(task({ owner_user_id: LAN, owner_name: "Bùi Ngọc Lan" }));
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    await openOwnerBox();
    await waitFor(() => expect(optionTexts()).toHaveLength(4));
    expect(optionTexts()).toEqual([
      "Tôi (Mai Anh)",
      "Giữ nguyên: Bùi Ngọc Lan",
      "Nguyễn Thanh Hà (Chủ phòng khám)",
      "BS. Lê Minh Tâm (Bác sĩ)",
    ]);
  });

  it("without an owner offers Tôi and everyone else, no Giữ nguyên", async () => {
    renderSheet(task());
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    await openOwnerBox();
    await waitFor(() => expect(optionTexts()).toHaveLength(4));
    expect(optionTexts()[0]).toBe("Tôi (Mai Anh)");
    expect(optionTexts().some((t) => t.startsWith("Giữ nguyên"))).toBe(false);
  });

  it("sends the colleague that was picked as the new owner", async () => {
    renderSheet(task());
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    const user = await openOwnerBox();
    await user.click(await screen.findByRole("option", { name: "Bùi Ngọc Lan (Quản lý)" }));
    await fillAndSave(user);
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const options = api.post.mock.calls[0]?.[1] as { body: { owner_user_id: string } };
    expect(options.body.owner_user_id).toBe(LAN);
  });

  it("keeps Tôi as the default owner", async () => {
    renderSheet(task({ owner_user_id: LAN, owner_name: "Bùi Ngọc Lan" }));
    const user = userEvent.setup();
    await fillAndSave(user);
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const options = api.post.mock.calls[0]?.[1] as { body: { owner_user_id: string } };
    expect(options.body.owner_user_id).toBe(ME);
  });

  it("keeps the current owner when Giữ nguyên is picked", async () => {
    renderSheet(task({ owner_user_id: LAN, owner_name: "Bùi Ngọc Lan" }));
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    const user = await openOwnerBox();
    await user.click(await screen.findByRole("option", { name: "Giữ nguyên: Bùi Ngọc Lan" }));
    await fillAndSave(user);
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const options = api.post.mock.calls[0]?.[1] as { body: { owner_user_id: string } };
    expect(options.body.owner_user_id).toBe(LAN);
  });

  it("still works with Tôi and Giữ nguyên when the staff list cannot be read", async () => {
    api.staff.mockReset().mockRejectedValue(new ApiError(403, "Không được phép"));
    renderSheet(task({ owner_user_id: LAN, owner_name: "Bùi Ngọc Lan" }));
    await screen.findByText(/Chưa tải được danh sách nhân viên/);
    await openOwnerBox();
    expect(optionTexts()).toEqual(["Tôi (Mai Anh)", "Giữ nguyên: Bùi Ngọc Lan"]);
  });

  it("says the colleagues are loading while keeping Tôi available", async () => {
    api.staff.mockReset().mockReturnValue(new Promise(() => undefined));
    renderSheet(task());
    expect(await screen.findByText("Đang tải danh sách nhân viên...")).toBeTruthy();
    await openOwnerBox();
    expect(optionTexts()).toEqual(["Tôi (Mai Anh)"]);
  });

  it("offers Thử lại when the colleagues cannot be read and lists them after a retry", async () => {
    api.staff.mockReset().mockRejectedValueOnce(new ApiError(429, "Quá nhiều lần"));
    api.staff.mockResolvedValue(STAFF);
    renderSheet(task());
    const user = userEvent.setup();
    await screen.findByText(/Chưa tải được danh sách nhân viên/);

    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    await waitFor(() => expect(screen.queryByText(/Chưa tải được danh sách nhân viên/)).toBeNull());
    await user.click(screen.getByLabelText("Phụ trách"));
    await waitFor(() => expect(optionTexts()).toHaveLength(4));
    expect(optionTexts()).toContain("BS. Lê Minh Tâm (Bác sĩ)");
  });

  it("never offers Chưa giao: a CRM task always has an owner", async () => {
    renderSheet(task({ owner_user_id: LAN, owner_name: "Bùi Ngọc Lan" }));
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    await openOwnerBox();
    await waitFor(() => expect(optionTexts()).toHaveLength(4));
    expect(optionTexts()).not.toContain("Chưa giao");
  });

  it("can be used with the keyboard alone: Enter opens, arrows move, Enter picks", async () => {
    renderSheet(task());
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    const user = userEvent.setup();
    const box = screen.getByLabelText("Phụ trách");
    await waitFor(() => expect(screen.queryByText("Đang tải danh sách nhân viên...")).toBeNull());
    box.focus();

    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(4));
    await user.keyboard("{ArrowDown}{Enter}");

    expect(box.textContent).toContain("Nguyễn Thanh Hà");
    await fillAndSave(user);
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const options = api.post.mock.calls[0]?.[1] as { body: { owner_user_id: string } };
    expect(options.body.owner_user_id).toBe(HA);
  });
});
