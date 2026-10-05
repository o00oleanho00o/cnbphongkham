// @vitest-environment jsdom
// The Patient 360 dialogs of step U9: the old sentences, what each one sends, and the rule that the brief is
// a draft over records that a person edits. The typed client is the network, the one dependency faked here.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AftercareDialog,
  BriefDialog,
  ExpectedReturnDialog,
  FactsDialog,
  MessageDialog,
} from "@/components/ops/patient/patient-dialogs";
import { PATIENT_ID, asRole, ok } from "@/components/ops/patient/test-support";
import type { Schemas } from "@/lib/api";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PUT: (...args: unknown[]) => api.put(...args),
    },
  };
});

const DATA = {
  patient: { id: PATIENT_ID, code: "P001", full_name: "Nguyễn Thu Hà", version: 1 },
  profile: {
    lifecycle_stage: "treating",
    marketing_opt_out: false,
    risk_level: "normal",
    expected_next_visit_at: "2026-10-01",
    expected_visit_source: "appointment",
  },
  plans: [],
  alerts: ["Da nhạy cảm"],
  consents: [{ id: "c1", kind: "media", granted: true }],
} as unknown as Schemas["Patient360"];

const sent = (mock: typeof api.post | typeof api.put): { body: unknown } =>
  mock.mock.calls[0]?.[1] as { body: unknown };

function view(node: React.ReactNode) {
  return render(asRole(["session.write", "consent.write"], node));
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(ok([]));
  api.post.mockReset().mockResolvedValue(ok({}));
  api.put.mockReset().mockResolvedValue(ok({}));
});

afterEach(() => cleanup());

describe("BriefDialog", () => {
  const draft = {
    text: "Nguyễn Thu Hà. Chưa có liệu trình được thiết lập.",
    source_ids: ["plan:1"],
    approved: null,
  };

  it("shows_the_draft_for_editing_with_the_source_notice", async () => {
    api.get.mockResolvedValue(ok(draft));
    view(<BriefDialog data={DATA} onClose={() => undefined} />);

    const box = await screen.findByLabelText("Brief mô phỏng · sửa trước khi duyệt");

    expect((box as HTMLTextAreaElement).value).toBe(draft.text);
    expect(
      screen.getByText(/Nguồn: Patient 360, events đã ghi nhận, follow-up đang mở\./),
    ).not.toBeNull();
  });

  it("the_doctor_approves_the_text_as_edited", async () => {
    api.get.mockResolvedValue(ok(draft));
    const closed = vi.fn();
    view(<BriefDialog data={DATA} onClose={closed} />);
    const user = userEvent.setup();

    const box = await screen.findByLabelText("Brief mô phỏng · sửa trước khi duyệt");
    await user.clear(box);
    await user.type(box, "Brief đã sửa");
    await user.click(screen.getByRole("button", { name: /Duyệt & lưu brief/ }));

    await waitFor(() => expect(sent(api.post).body).toEqual({ text: "Brief đã sửa" }));
    expect(closed).toHaveBeenCalled();
  });

  it("an_empty_brief_is_refused_in_place", async () => {
    api.get.mockResolvedValue(ok(draft));
    view(<BriefDialog data={DATA} onClose={() => undefined} />);
    const user = userEvent.setup();

    await user.clear(await screen.findByLabelText("Brief mô phỏng · sửa trước khi duyệt"));
    await user.click(screen.getByRole("button", { name: /Duyệt & lưu brief/ }));

    expect(screen.getByRole("alert").textContent).toBe("Brief không được để trống.");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("MessageDialog", () => {
  it("starts_with_the_greeting_of_the_old_web_and_sends_a_message_note", async () => {
    view(<MessageDialog data={DATA} onClose={() => undefined} onSent={() => undefined} />);

    const box = screen.getByLabelText("Nội dung") as HTMLTextAreaElement;
    expect(box.value).toBe(
      "Chào bạn Hà, Pema đã xem cập nhật của bạn. Da đang được theo dõi theo kế hoạch.",
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    await waitFor(() => expect(sent(api.post).body).toEqual({ kind: "message", body: box.value }));
  });

  it("an_empty_message_is_not_sent", async () => {
    view(<MessageDialog data={DATA} onClose={() => undefined} onSent={() => undefined} />);
    const user = userEvent.setup();

    await user.clear(screen.getByLabelText("Nội dung"));
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    expect(screen.getByRole("alert").textContent).toBe("Hãy nhập nội dung tin nhắn.");
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe("AftercareDialog", () => {
  it("opens_on_the_last_aftercare_that_was_sent", async () => {
    api.get.mockResolvedValue(
      ok([
        {
          id: "u1",
          kind: "aftercare",
          body: "SPF 50+ mỗi sáng",
          created_at: "2026-09-20T09:00:00+07:00",
        },
      ]),
    );
    view(
      <AftercareDialog patientId={PATIENT_ID} onClose={() => undefined} onSent={() => undefined} />,
    );

    const box = await screen.findByLabelText("Hướng dẫn đã duyệt cho người bệnh");

    expect((box as HTMLTextAreaElement).value).toBe("SPF 50+ mỗi sáng");
  });

  it("an_empty_text_is_refused_with_the_old_sentence", async () => {
    view(
      <AftercareDialog patientId={PATIENT_ID} onClose={() => undefined} onSent={() => undefined} />,
    );

    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: /Duyệt & gửi patient app/ }));

    expect(screen.getByRole("alert").textContent).toBe("Hãy nhập hướng dẫn.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("the_text_is_sent_as_aftercare", async () => {
    view(
      <AftercareDialog patientId={PATIENT_ID} onClose={() => undefined} onSent={() => undefined} />,
    );
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Hướng dẫn đã duyệt cho người bệnh"), "Dưỡng ẩm");
    await user.click(screen.getByRole("button", { name: /Duyệt & gửi patient app/ }));

    await waitFor(() =>
      expect(sent(api.post).body).toEqual({ kind: "aftercare", body: "Dưỡng ẩm" }),
    );
  });
});

describe("FactsDialog", () => {
  it("saves_one_warning_per_line_and_records_the_photo_consent_through_the_consent_action", async () => {
    view(
      <FactsDialog
        data={DATA}
        canRecordConsent
        onClose={() => undefined}
        onSaved={() => undefined}
      />,
    );
    const user = userEvent.setup();

    const box = screen.getByLabelText(/Cảnh báo · mỗi dòng một mục/);
    await user.clear(box);
    await user.type(box, "Dị ứng mẫu{enter}  Da nhạy cảm  ");
    await user.click(screen.getByLabelText("Có đồng ý sử dụng ảnh chăm sóc"));
    await user.click(screen.getByRole("button", { name: "Lưu thông tin" }));

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(sent(api.put).body).toEqual({ alerts: ["Dị ứng mẫu", "Da nhạy cảm"] });
    await waitFor(() =>
      expect(sent(api.post).body).toEqual({ kind: "media", granted: false, source: "Patient 360" }),
    );
  });

  it("the_consent_box_is_read_only_without_the_consent_permission", () => {
    view(
      <FactsDialog
        data={DATA}
        canRecordConsent={false}
        onClose={() => undefined}
        onSaved={() => undefined}
      />,
    );

    expect(
      (screen.getByLabelText("Có đồng ý sử dụng ảnh chăm sóc") as HTMLInputElement).disabled,
    ).toBe(true);
  });
});

describe("ExpectedReturnDialog", () => {
  it("an_empty_reason_shows_the_error_line_of_the_old_web_and_sends_nothing", async () => {
    view(<ExpectedReturnDialog data={DATA} onClose={() => undefined} onSaved={() => undefined} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Lưu ngày dự kiến" }));

    expect(screen.getByRole("alert").textContent).toBe(
      "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.",
    );
    expect(api.put).not.toHaveBeenCalled();
  });

  it("offers_the_four_typed_sources_and_never_the_appointment", () => {
    view(<ExpectedReturnDialog data={DATA} onClose={() => undefined} onSaved={() => undefined} />);

    const options = screen.getAllByRole("option").map((o) => o.textContent);

    expect(options).toEqual([
      "Bác sĩ khuyến nghị",
      "Protocol dịch vụ",
      "Kế hoạch điều trị",
      "Chăm sóc sau điều trị",
    ]);
  });

  it("a_valid_form_is_sent", async () => {
    view(<ExpectedReturnDialog data={DATA} onClose={() => undefined} onSaved={() => undefined} />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/Lý do/), "Bác sĩ hẹn đánh giá");
    await user.click(screen.getByRole("button", { name: "Lưu ngày dự kiến" }));

    await waitFor(() =>
      expect(sent(api.put).body).toEqual({
        date: "2026-10-01",
        reason: "Bác sĩ hẹn đánh giá",
        source: "doctor_recommendation",
      }),
    );
  });
});
