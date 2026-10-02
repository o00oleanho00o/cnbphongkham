// @vitest-environment jsdom
// The matrix editor and its role gate: CSKH never reaches it (no `care.matrix`: a plain note, no request), a
// doctor sees the badge "Chờ bác sĩ duyệt" and can approve, an edit is saved with the version that was read
// and the editor starts again from what the backend now holds, and cells that are always a person cannot be edited.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import CareMatrixPage from "./page";

const api = vi.hoisted(() => ({
  matrix: vi.fn(),
  saveMatrix: vi.fn(),
  approveMatrix: vi.fn(),
}));

vi.mock("@/lib/care/care-api", () => ({
  careApi: {
    matrix: (...args: unknown[]) => api.matrix(...args),
    saveMatrix: (...args: unknown[]) => api.saveMatrix(...args),
    approveMatrix: (...args: unknown[]) => api.approveMatrix(...args),
  },
}));

function matrix(over: Record<string, unknown> = {}) {
  return {
    pending_doctor_approval: true,
    can_edit: true,
    can_approve: true,
    version: 4,
    handoff: {
      confidence_threshold: 0.6,
      unverified_max_depth: "D1",
      post_procedure_window_hours: 48,
      repeat_question_threshold: 2,
      rows: [
        { signal: "default", from_depth: "D4" },
        { signal: "vip", from_depth: "D2" },
      ],
    },
    autonomy: {
      confidence_threshold: 0.85,
      appointment_confirm_l1: false,
      rules: [
        { action_type: "faq_kb_answer", hard_human: false, n_to_l2: 10, d3_enabled: false },
        { action_type: "medical_judgement", hard_human: true, n_to_l2: null, d3_enabled: false },
      ],
    },
    ...over,
  };
}

function renderPage(permissions: Permission[], role: "doctor" | "cs_staff" = "doctor") {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "BS. Lê Minh Tâm",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <CareMatrixPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

beforeEach(() => {
  api.matrix.mockReset().mockResolvedValue(matrix());
  api.saveMatrix.mockReset().mockResolvedValue(matrix({ version: 5 }));
  api.approveMatrix
    .mockReset()
    .mockResolvedValue(matrix({ version: 5, pending_doctor_approval: false }));
});

afterEach(cleanup);

describe("Care matrix page", () => {
  it("gives CSKH a plain note and makes no request", () => {
    renderPage(["care.read", "care.act"], "cs_staff");
    expect(screen.getByText(/không có quyền xem ma trận ngưỡng/)).toBeTruthy();
    expect(api.matrix).not.toHaveBeenCalled();
  });

  it("shows the pending badge and lets a doctor approve", async () => {
    renderPage(["care.matrix", "care.approve"]);
    expect(await screen.findByText("Chờ bác sĩ duyệt")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "Bác sĩ duyệt" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.setup().click(within(dialog).getByRole("button", { name: "Duyệt" }));
    await waitFor(() => expect(api.approveMatrix).toHaveBeenCalledWith(true, 4));
  });

  it("has no approve button when the backend says the caller cannot approve", async () => {
    api.matrix.mockResolvedValue(matrix({ can_approve: false }));
    renderPage(["care.matrix"]);
    await screen.findByText("Chờ bác sĩ duyệt");
    expect(screen.queryByRole("button", { name: "Bác sĩ duyệt" })).toBeNull();
  });

  it("is read only when the backend says the caller cannot edit", async () => {
    api.matrix.mockResolvedValue(matrix({ can_edit: false, can_approve: false }));
    renderPage(["care.matrix"]);
    await screen.findByText("Bạn chỉ xem được ma trận, không chỉnh được.");
    expect((screen.getByLabelText("Ngưỡng tin cậy của agent") as HTMLInputElement).disabled).toBe(
      true,
    );
    expect(screen.queryByRole("button", { name: "Lưu ma trận" })).toBeNull();
  });

  it("keeps the rules that are always a person out of reach", async () => {
    renderPage(["care.matrix", "care.approve"]);
    await screen.findByText("Chờ bác sĩ duyệt");
    const hard = screen.getByLabelText(
      "Lên L2 sau bao nhiêu lần, Nhận định y khoa",
    ) as HTMLInputElement;
    expect(hard.disabled).toBe(true);
    const soft = screen.getByLabelText(
      "Lên L2 sau bao nhiêu lần, Trả lời từ kho tri thức",
    ) as HTMLInputElement;
    expect(soft.disabled).toBe(false);
  });

  it("saves with the version that was read and refuses a number that is not one", async () => {
    renderPage(["care.matrix", "care.approve"]);
    const user = userEvent.setup();
    const field = (await screen.findByLabelText("Ngưỡng tin cậy của agent")) as HTMLInputElement;
    const save = screen.getByRole("button", { name: "Lưu ma trận" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    await user.clear(field);
    await user.type(field, "abc");
    expect(save.disabled).toBe(true);
    expect(screen.getByText(/Ngưỡng tin cậy của agent là số từ 0 đến 1/)).toBeTruthy();

    await user.clear(field);
    await user.type(field, "0,7");
    expect(save.disabled).toBe(false);
    await user.click(save);

    await waitFor(() => expect(api.saveMatrix).toHaveBeenCalledTimes(1));
    const body = api.saveMatrix.mock.calls[0]?.[0] as {
      version: number;
      handoff: { confidence_threshold: number };
    };
    expect(body.version).toBe(4);
    expect(body.handoff.confidence_threshold).toBe(0.7);
  });
});
