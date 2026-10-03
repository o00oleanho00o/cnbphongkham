// @vitest-environment jsdom
// The Kế hoạch tab: plans with their progress and the old "Điều chỉnh kế hoạch" form. The BE repeats the rules.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlanTab } from "@/components/ops/patient/plan-tab";
import { PATIENT_ID, asRole, ok, plan } from "@/components/ops/patient/test-support";
import { TOTAL_BELOW_DONE_MESSAGE } from "@/lib/ops/plan-form";

const api = vi.hoisted(() => ({ post: vi.fn(), patch: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      POST: (...args: unknown[]) => api.post(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
    },
  };
});

function renderTab(canWrite: boolean, onChanged: () => void = () => undefined) {
  return render(
    asRole(
      ["patient.read_360", "session.write"],
      <PlanTab
        patientId={PATIENT_ID}
        plans={[plan()]}
        doctorName="BS. Lê Minh Tâm"
        nextVisit="2026-10-29T09:00:00+07:00"
        canWrite={canWrite}
        onChanged={onChanged}
      />,
    ),
  );
}

beforeEach(() => {
  api.post.mockReset().mockResolvedValue(ok(plan()));
  api.patch.mockReset().mockResolvedValue(ok(plan()));
});

afterEach(() => cleanup());

describe("PlanTab", () => {
  it("lists_every_planned_session_with_its_state", () => {
    renderTab(true);

    expect(screen.getAllByText(/^Buổi \d · /).map((el) => el.textContent)).toEqual([
      "Buổi 1 · Đã hoàn tất",
      "Buổi 2 · Đã hoàn tất",
      "Buổi 3 · Tiếp theo",
      "Buổi 4 · Dự kiến",
    ]);
  });

  it("shows_the_progress_of_the_plan", () => {
    renderTab(false);

    expect(screen.getByRole("progressbar", { name: /Tiến độ/ }).getAttribute("aria-valuenow")).toBe(
      "50",
    );
  });

  it("someone_who_cannot_write_has_no_edit_button", () => {
    renderTab(false);

    expect(screen.queryByRole("button", { name: "Chỉnh sửa" })).toBeNull();
  });

  it("a_total_below_the_sessions_done_is_refused_before_anything_is_sent", async () => {
    renderTab(true);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Chỉnh sửa" }));
    const total = screen.getByLabelText(/Tổng số buổi/);
    await user.clear(total);
    await user.type(total, "1");
    await user.click(screen.getByRole("button", { name: "Lưu kế hoạch" }));

    expect(screen.getByRole("alert").textContent).toBe(TOTAL_BELOW_DONE_MESSAGE);
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("the_edit_sends_the_version_that_was_read", async () => {
    const changed = vi.fn();
    renderTab(true, changed);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Chỉnh sửa" }));
    const total = screen.getByLabelText(/Tổng số buổi/);
    await user.clear(total);
    await user.type(total, "6");
    await user.click(screen.getByRole("button", { name: "Lưu kế hoạch" }));

    await waitFor(() => expect(changed).toHaveBeenCalled());
    const sent = (
      api.patch.mock.calls[0]?.[1] as { body: { version: number; total_sessions: number } }
    ).body;
    expect([sent.version, sent.total_sessions]).toEqual([3, 6]);
  });
});
