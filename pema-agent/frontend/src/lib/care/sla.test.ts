import { describe, expect, it } from "vitest";

import { ageText, slaState } from "@/lib/care/sla";

const NOW = new Date("2026-10-02T09:00:00+07:00");
const at = (minutes: number) => new Date(NOW.getTime() + minutes * 60_000).toISOString();

describe("slaState", () => {
  it("counts the minutes left and marks the last five as soon", () => {
    expect(slaState(at(24), NOW)).toEqual({ text: "Còn 24 phút", overdue: false, soon: false });
    expect(slaState(at(3), NOW)).toEqual({ text: "Còn 3 phút", overdue: false, soon: true });
  });

  it("says hours and minutes beyond an hour", () => {
    expect(slaState(at(90), NOW)?.text).toBe("Còn 1 giờ 30 phút");
    expect(slaState(at(120), NOW)?.text).toBe("Còn 2 giờ");
  });

  it("is overdue at and after the deadline", () => {
    expect(slaState(at(0), NOW)).toEqual({ text: "Quá hạn 1 phút", overdue: true, soon: false });
    expect(slaState(at(-7), NOW)?.text).toBe("Quá hạn 7 phút");
  });

  it("is null without a deadline or with a broken one", () => {
    expect(slaState(null, NOW)).toBeNull();
    expect(slaState("not a date", NOW)).toBeNull();
  });
});

describe("ageText", () => {
  it("words minutes, hours and days", () => {
    expect(ageText(at(-0.2), NOW)).toBe("Vừa xong");
    expect(ageText(at(-6), NOW)).toBe("6 phút trước");
    expect(ageText(at(-125), NOW)).toBe("2 giờ trước");
    expect(ageText(at(-3 * 24 * 60), NOW)).toBe("3 ngày trước");
  });
});
