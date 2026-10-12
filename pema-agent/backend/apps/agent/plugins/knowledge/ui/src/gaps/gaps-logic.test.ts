import { describe, expect, it } from "vitest";

import type { Gap } from "../types";
import { answerDraft, countText, emptyTitle, relativeTime, withoutGap } from "./gaps-logic";

const NOW = new Date("2026-10-12T08:30:00+07:00");

describe("relativeTime", () => {
  it.each([
    ["2026-10-12T08:29:40+07:00", "vừa xong"],
    ["2026-10-12T08:25:00+07:00", "5 phút trước"],
    ["2026-10-12T05:30:00+07:00", "3 giờ trước"],
    ["2026-10-11T07:00:00+07:00", "hôm qua"],
    ["2026-10-08T08:30:00+07:00", "4 ngày trước"],
  ])("reads_%s_as_%s", (iso, expected) => {
    expect(relativeTime(iso, NOW)).toBe(expected);
  });

  it("falls_back_to_the_date_after_a_month", () => {
    expect(relativeTime("2026-08-01T10:00:00+07:00", NOW)).toBe("01/08/2026");
  });
});

describe("answerDraft", () => {
  it("starts_the_text_with_the_question_as_a_heading", () => {
    expect(answerDraft("  có làm laser trị sẹo rỗ không ")).toEqual({
      title: "có làm laser trị sẹo rỗ không",
      text: "# có làm laser trị sẹo rỗ không\n\n",
    });
  });
});

describe("lists", () => {
  it("drops_one_gap_by_id", () => {
    const gap = (id: string): Gap => ({ id, question: "q", count: 1, channel: "c", last_asked_at: "", state: "open" });
    expect(withoutGap([gap("a"), gap("b")], "a").map((item) => item.id)).toEqual(["b"]);
  });

  it("has_a_sentence_for_every_empty_filter", () => {
    expect(emptyTitle("open")).toBe("Chưa có câu hỏi nào bị bỏ sót");
    expect(emptyTitle("ignored")).not.toBe(emptyTitle("answered"));
    expect(countText(7)).toBe("7 lần");
  });
});
