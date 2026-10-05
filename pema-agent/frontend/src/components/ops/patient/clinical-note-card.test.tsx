// @vitest-environment jsdom
// The "Tiền sử & chẩn đoán" card: both texts are required, the doctor's own words are what is sent, and a reader
// without `session.write` cannot edit. The typed client is the network, the one dependency faked here.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClinicalNoteCard } from "@/components/ops/patient/clinical-note-card";
import { PATIENT_ID, asRole, ok } from "@/components/ops/patient/test-support";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      PUT: (...args: unknown[]) => api.put(...args),
    },
  };
});

const EMPTY = { history: "", diagnosis: "", reviewed_by_name: null, reviewed_at: null };

function renderCard(canWrite: boolean) {
  return render(
    asRole(
      ["session.read", "session.write"],
      <ClinicalNoteCard patientId={PATIENT_ID} canWrite={canWrite} onChanged={() => undefined} />,
    ),
  );
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok(EMPTY));
  api.put.mockReset().mockResolvedValue(ok(EMPTY));
});

afterEach(() => cleanup());

describe("ClinicalNoteCard", () => {
  it("states_that_the_doctor_writes_it_and_no_model_diagnoses", async () => {
    renderCard(true);

    expect(await screen.findByText("Bác sĩ ghi nhận, không dùng AI tự chẩn đoán")).not.toBeNull();
  });

  it("saving_with_an_empty_diagnosis_gives_the_old_sentence_and_sends_nothing", async () => {
    renderCard(true);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/Tiền sử đã khai thác/), "Nám hai bên má");
    await user.click(screen.getByRole("button", { name: "Bác sĩ lưu nhận định" }));

    expect(screen.getByRole("alert").textContent).toBe(
      "Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.",
    );
    expect(api.put).not.toHaveBeenCalled();
  });

  it("both_texts_are_sent_as_the_doctor_typed_them", async () => {
    renderCard(true);
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText(/Tiền sử đã khai thác/), "Nám hai bên má");
    await user.type(screen.getByLabelText(/Khám \/ chẩn đoán/), "Tăng sắc tố sau viêm");
    await user.click(screen.getByRole("button", { name: "Bác sĩ lưu nhận định" }));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect((api.put.mock.calls[0]?.[1] as { body: unknown }).body).toEqual({
      history: "Nám hai bên má",
      diagnosis: "Tăng sắc tố sau viêm",
    });
  });

  it("a_reader_sees_the_texts_read_only_without_the_save_button", async () => {
    api.get.mockResolvedValue(ok({ ...EMPTY, history: "Tiền sử mẫu", diagnosis: "Nhận định mẫu" }));
    renderCard(false);

    const history = await screen.findByLabelText(/Tiền sử đã khai thác/);

    expect((history as HTMLTextAreaElement).readOnly).toBe(true);
    expect(screen.queryByRole("button", { name: "Bác sĩ lưu nhận định" })).toBeNull();
  });
});
