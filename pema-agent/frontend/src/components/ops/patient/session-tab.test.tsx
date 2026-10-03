// @vitest-environment jsdom
// The Buổi điều trị tab: the form of the old "Ghi buổi điều trị" and the rules it checks before it calls the BE.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionTab } from "@/components/ops/patient/session-tab";
import { PATIENT_ID, asRole, ok, plan } from "@/components/ops/patient/test-support";
import type { Schemas } from "@/lib/api";
import {
  AFTERCARE_REQUIRED_MESSAGE,
  NOTE_REQUIRED_MESSAGE,
  PLAN_FULL_MESSAGE,
} from "@/lib/ops/session-form";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
    },
  };
});

const SAVED = {
  id: "session-1",
  patient_id: PATIENT_ID,
  plan_id: "plan-1",
  performed_at: "2026-09-20T09:00:00+07:00",
  doctor_id: null,
  title: "Buổi 3/4 · Laser CO2 phục hồi da",
  status: "completed",
  version: 2,
} as Schemas["SessionDetailOut"];

function renderTab(plans = [plan()], canWrite = true) {
  return render(
    asRole(
      ["session.read", "session.write"],
      <SessionTab
        patientId={PATIENT_ID}
        plans={plans}
        alerts={[]}
        consentGranted
        canWrite={canWrite}
        canRecordConsent
        canUpload
        canReadMedia
        onSaved={() => undefined}
      />,
    ),
  );
}

const sentBody = (): Record<string, unknown> =>
  (api.post.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;

async function fill(user: ReturnType<typeof userEvent.setup>, note: string, aftercare: string) {
  await user.type(await screen.findByLabelText("Đánh giá trước buổi"), note);
  await user.type(screen.getByLabelText("Hướng dẫn chăm sóc gửi sau buổi"), aftercare);
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok([]));
  api.post.mockReset().mockResolvedValue(ok(SAVED));
});

afterEach(() => cleanup());

describe("SessionTab", () => {
  it("has_the_fields_of_the_old_form", async () => {
    renderTab();
    await screen.findByLabelText("Đánh giá trước buổi");

    const labels = [
      "Ngày",
      "Loại buổi",
      "Protocol chăm sóc",
      "Ngày dự kiến tái khám",
      "Hướng dẫn chăm sóc gửi sau buổi",
      "Vùng chụp",
      "Góc chụp",
      "Ảnh mốc",
    ];

    expect(labels.map((label) => screen.queryByLabelText(label) !== null)).toEqual(
      labels.map(() => true),
    );
  });

  it("counts_the_next_session_of_the_plan_in_the_header", async () => {
    renderTab();

    expect(await screen.findByText("3/4 dự kiến")).toBeTruthy();
  });

  it("the_assessment_is_required_before_anything_is_sent", async () => {
    renderTab();

    await userEvent.setup().click(await screen.findByRole("button", { name: /Lưu buổi điều trị/ }));

    expect(screen.getByRole("alert").textContent).toBe(NOTE_REQUIRED_MESSAGE);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("the_aftercare_text_is_required_too", async () => {
    renderTab();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Đánh giá trước buổi"), "Da ổn");
    await user.click(screen.getByRole("button", { name: /Lưu buổi điều trị/ }));

    expect(screen.getByRole("alert").textContent).toBe(AFTERCARE_REQUIRED_MESSAGE);
  });

  it("a_plan_with_all_its_sessions_refuses_a_new_one", async () => {
    renderTab([plan({ completed_sessions: 4 })]);
    const user = userEvent.setup();

    await fill(user, "Da ổn", "Dưỡng ẩm");
    await user.click(screen.getByRole("button", { name: /Lưu buổi điều trị/ }));

    expect(screen.getByRole("alert").textContent).toBe(PLAN_FULL_MESSAGE);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("a_complete_form_records_a_completed_session_on_the_chosen_plan", async () => {
    renderTab();
    const user = userEvent.setup();

    await fill(user, "Da ổn", "Dưỡng ẩm");
    await user.click(screen.getByRole("button", { name: /Lưu buổi điều trị/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(sentBody()).toMatchObject({
      plan_id: "plan-1",
      complete: true,
      with_photo: false,
      protocol_id: "laser-co2",
      note: "Da ổn",
      aftercare: "Dưỡng ẩm",
    });
  });

  it("someone_who_cannot_write_sees_the_recorded_sessions_but_no_form", async () => {
    api.get.mockResolvedValue(ok([{ ...SAVED, note: "Đỏ giảm (mẫu)" }]));
    renderTab([plan()], false);

    expect(await screen.findByText("Đỏ giảm (mẫu)")).toBeTruthy();
    expect(screen.queryByLabelText("Đánh giá trước buổi")).toBeNull();
  });
});
