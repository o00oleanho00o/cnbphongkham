// @vitest-environment jsdom
// The Tư vấn tab: key points become a draft on the BE, the clinician edits the draft and approves it. The BE owns
// the draft text and the approval; these tests only drive the screen against a fake of the typed client.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ConsultTab,
  DRAFT_EMPTY_MESSAGE,
  POINTS_REQUIRED_MESSAGE,
} from "@/components/ops/patient/consult-tab";
import { PATIENT_ID, asRole, ok } from "@/components/ops/patient/test-support";
import type { Schemas } from "@/lib/api";

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

type Note = Schemas["ConsultNoteOut"];

const note = (overrides: Partial<Note> = {}): Note => ({
  id: "note-1",
  patient_id: PATIENT_ID,
  status: "draft",
  source_text: "Da ổn hơn",
  body: "Bản nháp ghi chú · 20/09/2026: Da ổn hơn",
  created_at: "2026-09-20T09:00:00+07:00",
  version: 1,
  ...overrides,
});

const sentBody = (): unknown => (api.post.mock.calls[0]?.[1] as { body: unknown }).body;

function renderTab(canWrite: boolean, onChanged: () => void = () => undefined) {
  return render(
    asRole(
      ["session.read", "session.write"],
      <ConsultTab patientId={PATIENT_ID} canWrite={canWrite} onChanged={onChanged} />,
    ),
  );
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok([]));
  api.post.mockReset().mockResolvedValue(ok(note()));
});

afterEach(() => cleanup());

describe("ConsultTab", () => {
  it("asks_for_a_few_key_points_before_making_a_draft", async () => {
    renderTab(true);

    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Tạo bản nháp ghi chú" }));

    expect(screen.getByRole("alert").textContent).toBe(POINTS_REQUIRED_MESSAGE);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("the_typed_points_are_sent_to_make_a_draft", async () => {
    renderTab(true);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/Ghi chú ngắn/), "Da ổn hơn, đỏ giảm");
    await user.click(screen.getByRole("button", { name: "Tạo bản nháp ghi chú" }));

    await waitFor(() => expect(sentBody()).toEqual({ input_text: "Da ổn hơn, đỏ giảm" }));
  });

  it("the_edited_draft_is_what_gets_approved_with_the_version_that_was_read", async () => {
    api.get.mockResolvedValue(ok([note({ version: 4 })]));
    const changed = vi.fn();
    renderTab(true, changed);
    const user = userEvent.setup();

    const draft = await screen.findByLabelText("Chỉnh sửa bản nháp");
    await user.clear(draft);
    await user.type(draft, "Ghi chú đã chỉnh");
    await user.click(screen.getByRole("button", { name: /Duyệt/ }));

    await waitFor(() => expect(sentBody()).toEqual({ version: 4, body: "Ghi chú đã chỉnh" }));
    expect(changed).toHaveBeenCalled();
  });

  it("an_emptied_draft_cannot_be_approved", async () => {
    api.get.mockResolvedValue(ok([note()]));
    renderTab(true);
    const user = userEvent.setup();

    await user.clear(await screen.findByLabelText("Chỉnh sửa bản nháp"));
    await user.click(screen.getByRole("button", { name: /Duyệt/ }));

    expect(screen.getByRole("alert").textContent).toBe(DRAFT_EMPTY_MESSAGE);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("someone_who_cannot_write_only_reads_the_approved_notes", async () => {
    api.get.mockResolvedValue(
      ok([
        note({
          id: "n2",
          status: "approved",
          body: "Ghi chú đã duyệt (mẫu)",
          approved_at: "2026-09-21T09:00:00+07:00",
          approved_by_name: "BS. Mai",
        }),
      ]),
    );
    renderTab(false);

    expect(await screen.findByText("Ghi chú đã duyệt (mẫu)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Tạo bản nháp ghi chú" })).toBeNull();
  });
});
