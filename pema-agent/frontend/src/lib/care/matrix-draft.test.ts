import { describe, expect, it } from "vitest";

import type { CareMatrix } from "@/lib/care/care-types";
import { setAutonomyRule, setDepthRow } from "@/lib/care/forms";
import { buildMatrix, editOf, textOf } from "@/lib/care/matrix-draft";

const MATRIX: CareMatrix = {
  pending_doctor_approval: true,
  can_edit: true,
  can_approve: true,
  version: 3,
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
};

describe("buildMatrix", () => {
  it("rebuilds the saved matrix from its own text", () => {
    const built = buildMatrix(MATRIX, editOf(MATRIX), textOf(MATRIX));
    expect(built.error).toBe("");
    expect(built.value).toEqual({
      version: 3,
      handoff: MATRIX.handoff,
      autonomy: MATRIX.autonomy,
    });
  });

  it("takes typed numbers and edited cells", () => {
    const text = { ...textOf(MATRIX), handoffConfidence: "0,7", nToL2: { faq_kb_answer: "20" } };
    const edit = {
      ...editOf(MATRIX),
      handoff: setDepthRow(MATRIX.handoff, "vip", "D3"),
    };
    const built = buildMatrix(MATRIX, edit, text);
    expect(built.value?.handoff.confidence_threshold).toBe(0.7);
    expect(built.value?.handoff.rows[1]).toEqual({ signal: "vip", from_depth: "D3" });
    expect(built.value?.autonomy.rules[0]?.n_to_l2).toBe(20);
  });

  it("reports the first number that is not one and builds nothing", () => {
    const bad = buildMatrix(MATRIX, editOf(MATRIX), { ...textOf(MATRIX), handoffConfidence: "2" });
    expect(bad.value).toBeNull();
    expect(bad.error).toContain("0 đến 1");
    const worse = buildMatrix(MATRIX, editOf(MATRIX), {
      ...textOf(MATRIX),
      nToL2: { faq_kb_answer: "abc" },
    });
    expect(worse.value).toBeNull();
  });

  it("empty text means no L2 promotion for that type, and a hard rule is always none", () => {
    const text = { ...textOf(MATRIX), nToL2: { faq_kb_answer: "", medical_judgement: "5" } };
    const built = buildMatrix(MATRIX, editOf(MATRIX), text);
    expect(built.value?.autonomy.rules.map((r) => r.n_to_l2)).toEqual([null, null]);
  });
});

describe("setAutonomyRule", () => {
  it("never edits a rule that is always a person", () => {
    const changed = setAutonomyRule(MATRIX.autonomy, "medical_judgement", { d3_enabled: true });
    expect(changed.rules[1]?.d3_enabled).toBe(false);
    const open = setAutonomyRule(MATRIX.autonomy, "faq_kb_answer", { d3_enabled: true });
    expect(open.rules[0]?.d3_enabled).toBe(true);
    expect(MATRIX.autonomy.rules[0]?.d3_enabled).toBe(false);
  });
});
