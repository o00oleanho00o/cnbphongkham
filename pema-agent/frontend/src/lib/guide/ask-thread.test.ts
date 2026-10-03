import { describe, expect, it } from "vitest";

import {
  answeredTurn,
  askedTurn,
  cleanQuestion,
  failedTurn,
  MAX_QUESTION_LENGTH,
  type AskHit,
} from "./ask-thread";

const HIT: AskHit = {
  article_id: "guide-1",
  article_title: "Bắt đầu theo vai trò",
  heading: "Cách thực hiện",
  passage: "1. Lễ tân: tìm đúng hồ sơ.",
  score: 1.5,
};

describe("cleanQuestion", () => {
  it("trims_and_collapses_blanks", () => {
    expect(cleanQuestion("  làm   sao \n dời lịch  ")).toBe("làm sao dời lịch");
  });

  it("is_empty_for_blanks_only", () => {
    expect(cleanQuestion(" \n\t ")).toBe("");
  });

  it("is_cut_to_the_length_the_api_accepts", () => {
    expect(cleanQuestion("a".repeat(MAX_QUESTION_LENGTH + 40))).toHaveLength(MAX_QUESTION_LENGTH);
  });
});

describe("the conversation", () => {
  it("a_new_question_waits_for_its_answer", () => {
    expect(askedTurn([], 1, "dời lịch")).toEqual([
      { id: 1, question: "dời lịch", state: "loading", hits: [], error: "" },
    ]);
  });

  it("an_answer_fills_only_its_own_turn", () => {
    const turns = askedTurn(askedTurn([], 1, "a"), 2, "b");
    const after = answeredTurn(turns, 2, [HIT]);
    expect(after.map((t) => t.state)).toEqual(["loading", "done"]);
    expect(after[1]?.hits).toEqual([HIT]);
  });

  it("a_failure_keeps_the_question_and_says_why", () => {
    const after = failedTurn(askedTurn([], 1, "a"), 1, "Không kết nối được server");
    expect(after[0]).toMatchObject({
      question: "a",
      state: "error",
      error: "Không kết nối được server",
    });
  });
});
