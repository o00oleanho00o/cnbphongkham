import { describe, expect, it } from "vitest";

import {
  addDays,
  createBody,
  dayTitle,
  emptyForm,
  endShiftText,
  entriesOn,
  isOvernight,
  momentTitle,
  mondayOf,
  overnightText,
  toggleWeekday,
  updateBody,
  validateRoster,
  weekDates,
  weekTitle,
  weekdayOf,
} from "./roster-view";

const entry = (over: Partial<Parameters<typeof entriesOn>[0][number]>) => ({
  id: "e1",
  account_id: "long",
  user_id: "u1",
  user_name: "Mai Anh",
  user_role: "cs_staff" as const,
  weekdays: ["mon", "tue"] as ("mon" | "tue")[] | null,
  on_date: null as string | null,
  start: "08:00",
  end: "12:00",
  note: null,
  version: 1,
  ...over,
});

describe("the week", () => {
  it("starts on the Monday that holds a Sunday date", () => {
    expect(mondayOf("2026-09-20")).toBe("2026-09-14");
  });

  it("lists the seven days from the Monday", () => {
    expect(weekDates("2026-09-14")).toEqual([
      "2026-09-14",
      "2026-09-15",
      "2026-09-16",
      "2026-09-17",
      "2026-09-18",
      "2026-09-19",
      "2026-09-20",
    ]);
  });

  it("moves across a month end", () => {
    expect(addDays("2026-09-28", 7)).toBe("2026-10-05");
    expect(weekdayOf("2026-10-05")).toBe("mon");
  });

  it("words the titles as the frames do", () => {
    expect(dayTitle("2026-09-14")).toBe("T2, 14/09");
    expect(dayTitle("2026-09-20")).toBe("CN, 20/09");
    expect(weekTitle("2026-09-14")).toBe("Tuần 14/09 – 20/09/2026");
    expect(momentTitle("2026-09-20", "09:00")).toBe("Chủ nhật 20/09/2026 · 09:00");
  });
});

describe("entriesOn", () => {
  it("shows a weekly shift on each of its weekdays and a one-day shift only on its date", () => {
    const weekly = entry({});
    const single = entry({ id: "e2", weekdays: null, on_date: "2026-09-16", start: "07:00" });
    expect(entriesOn([weekly, single], "2026-09-14").map((e) => e.id)).toEqual(["e1"]);
    expect(entriesOn([weekly, single], "2026-09-16").map((e) => e.id)).toEqual(["e2"]);
    expect(entriesOn([weekly, single], "2026-09-15").map((e) => e.id)).toEqual(["e1"]);
  });

  it("orders a day by start time", () => {
    const late = entry({ id: "late", start: "12:00", end: "17:00" });
    const early = entry({ id: "early" });
    expect(entriesOn([late, early], "2026-09-14").map((e) => e.id)).toEqual(["early", "late"]);
  });
});

describe("the form", () => {
  it("starts on Monday to Friday, 08:00 to 12:00, or on the weekday of the day it was opened from", () => {
    expect(emptyForm("long", "u1").weekdays).toEqual(["mon", "tue", "wed", "thu", "fri"]);
    expect(emptyForm("long", "u1", "sat").weekdays).toEqual(["sat"]);
  });

  it("refuses equal times, as the frame WM36 shows", () => {
    const form = { ...emptyForm("long", "u1"), start: "12:00", end: "12:00" };
    expect(validateRoster(form).time).toBe("Giờ bắt đầu và giờ kết thúc phải khác nhau.");
  });

  it("refuses a weekly shift without a weekday and a one-day shift without a date", () => {
    expect(validateRoster({ ...emptyForm("long", "u1"), weekdays: [] }).weekdays).toBeDefined();
    expect(validateRoster({ ...emptyForm("long", "u1"), mode: "date" }).date).toBeDefined();
  });

  it("knows a shift that ends the next morning and says so in the words of each mode", () => {
    const night = { ...emptyForm("long", "u1"), start: "22:00", end: "06:00" };
    expect(isOvernight(night)).toBe(true);
    expect(overnightText(night)).toBe("Giờ đến nhỏ hơn giờ từ: ca kết thúc vào sáng hôm sau.");
    expect(overnightText({ ...night, mode: "date", date: "2026-09-22" })).toBe(
      "Ca kết thúc vào 06:00 sáng hôm sau.",
    );
    expect(overnightText(emptyForm("long", "u1"))).toBeNull();
  });

  it("keeps the weekdays in week order when a day is switched", () => {
    expect(toggleWeekday(["mon", "wed"], "tue")).toEqual(["mon", "tue", "wed"]);
    expect(toggleWeekday(["mon", "tue"], "mon")).toEqual(["tue"]);
  });

  it("builds a create body with either weekdays or a date, never both", () => {
    const weekly = createBody({ ...emptyForm("long", "u1"), note: " trực thay " });
    expect(weekly).toMatchObject({
      weekdays: ["mon", "tue", "wed", "thu", "fri"],
      on_date: null,
      note: "trực thay",
    });
    const single = createBody({ ...emptyForm("long", "u1"), mode: "date", date: "2026-09-22" });
    expect(single).toMatchObject({ weekdays: null, on_date: "2026-09-22", note: null });
  });

  it("sends the version the person saw when it saves an edit", () => {
    expect(updateBody(emptyForm("long", "u1"), 3).version).toBe(3);
  });
});

describe("endShiftText", () => {
  it("counts where the threads went", () => {
    expect(endShiftText({ user_id: "u", rerouted: 4, to_queue: 1, skipped: 0 })).toBe(
      "Đã kết thúc ca: 4 hội thoại chuyển người trực, 1 về hàng chờ, 0 bỏ qua.",
    );
  });
});
