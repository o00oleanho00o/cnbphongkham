// @vitest-environment jsdom
// "Trả lại cho agent": the levels offered are the ones the backend lists, the consequence under the form is the
// backend's own sentence (and a refused combination blocks the button), only the person who holds the conversation
// gets a form, and the release is sent with the note, the level and the days.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReleaseForm } from "@/components/care/release-form";
import { ToastProvider } from "@/components/ops/toast";
import type { PatientCareTimeline } from "@/lib/care/care-types";

const api = vi.hoisted(() => ({ preview: vi.fn(), release: vi.fn() }));

vi.mock("@/lib/care/care-api", () => ({
  careApi: {
    previewRelease: (...args: unknown[]) => api.preview(...args),
    release: (...args: unknown[]) => api.release(...args),
  },
}));

const PATIENT = "00000000-0000-4000-8002-000000000007";

function timeline(over: Partial<PatientCareTimeline> = {}): PatientCareTimeline {
  return {
    patient_id: PATIENT,
    patient_name: "Khách Bảy",
    control: {
      state: "STAFF",
      since: "2026-10-02T07:00:00+07:00",
      staff_owner_id: "u-1",
      staff_owner_name: "Mai Anh",
    },
    autonomy: { effective_level: "L1", base_level: "L1", paused: false },
    pending_drafts: [],
    paused_reminders: [],
    entries: [],
    memory: [],
    can_release: true,
    can_tell_agent: true,
    release_levels: ["L0", "L1"],
    max_override_days: 30,
    ...over,
  };
}

function renderForm(t: PatientCareTimeline, onDone = vi.fn()) {
  render(
    <ToastProvider>
      <ReleaseForm patientId={PATIENT} timeline={t} onDone={onDone} />
    </ToastProvider>,
  );
  return onDone;
}

beforeEach(() => {
  api.preview
    .mockReset()
    .mockImplementation((_id: string, body: { level: string | null; days: number | null }) =>
      Promise.resolve(
        body.level
          ? {
              allowed: true,
              consequence: `Trong ${body.days} ngày agent chỉ làm ở mức ${body.level}.`,
            }
          : { allowed: true, consequence: "Agent tiếp tục ở mức L1." },
      ),
    );
  api.release.mockReset().mockResolvedValue({ patient_id: PATIENT, state: "AUTO" });
});

afterEach(cleanup);

describe("ReleaseForm", () => {
  it("offers keep plus the levels the backend lists, never a higher one", async () => {
    renderForm(timeline());
    await screen.findByText(/Agent tiếp tục ở mức L1/);
    expect(screen.getByLabelText("Giữ mức hiện tại của agent")).toBeTruthy();
    expect(screen.getByLabelText(/Hạ xuống L0/)).toBeTruthy();
    expect(screen.getByLabelText(/Hạ xuống L1/)).toBeTruthy();
    expect(screen.queryByLabelText(/Hạ xuống L2/)).toBeNull();
  });

  it("shows the consequence the backend words, for the level and days chosen", async () => {
    renderForm(timeline());
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/Hạ xuống L0/));
    await user.clear(screen.getByLabelText("Số ngày áp dụng"));
    await user.type(screen.getByLabelText("Số ngày áp dụng"), "3");
    expect(await screen.findByText(/Trong 3 ngày agent chỉ làm ở mức L0/)).toBeTruthy();
  });

  it("blocks the button when the backend does not allow the combination", async () => {
    api.preview.mockResolvedValue({
      allowed: false,
      consequence: "Khi trả lại chỉ được giữ nguyên hoặc hạ mức.",
    });
    renderForm(timeline());
    await screen.findByText(/chỉ được giữ nguyên hoặc hạ mức/);
    expect(
      (screen.getByRole("button", { name: "Trả lại cho agent" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("asks for the days before it asks the backend", async () => {
    renderForm(timeline());
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/Hạ xuống L0/));
    await user.clear(screen.getByLabelText("Số ngày áp dụng"));
    expect(screen.getByText("Hãy nhập số ngày áp dụng mức đã chọn.")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Trả lại cho agent" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("confirms, then sends the note, the level and the days", async () => {
    const onDone = renderForm(timeline());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Ghi chú bàn giao"), "Khách ổn, tiếp tục");
    await user.click(screen.getByLabelText(/Hạ xuống L0/));
    await screen.findByText(/Trong 7 ngày agent chỉ làm ở mức L0/);
    await user.click(screen.getByRole("button", { name: "Trả lại cho agent" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Trả lại" }));

    await waitFor(() =>
      expect(api.release).toHaveBeenCalledWith(PATIENT, {
        note: "Khách ổn, tiếp tục",
        level: "L0",
        days: 7,
      }),
    );
    expect(onDone).toHaveBeenCalled();
  });

  it("gives a person who does not hold the conversation a note instead of a form", () => {
    renderForm(timeline({ can_release: false }));
    expect(
      screen.getByText(/Chỉ người đang phụ trách cuộc trò chuyện mới trả lại cho agent được/),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Trả lại cho agent" })).toBeNull();
    expect(api.preview).not.toHaveBeenCalled();
  });
});
