import { describe, expect, it } from "vitest";

import {
  ageYears,
  clinicDateKey,
  daysBetween,
  dueLabel,
  formatDateTime,
  isOverdue,
  localInputToIso,
} from "./format";

// 2026-09-20 09:00 in Vietnam = 02:00 UTC
const NOW = new Date("2026-09-20T02:00:00Z");

describe("clinic dates", () => {
  it("late_evening_utc_is_already_the_next_day_in_vietnam", () => {
    expect(clinicDateKey(new Date("2026-09-19T18:30:00Z"))).toBe("2026-09-20");
  });

  it("days_between_counts_clinic_calendar_days", () => {
    expect(daysBetween(NOW, new Date("2026-09-22T03:00:00+07:00"))).toBe(2);
  });
});

describe("date and time text", () => {
  it("a_datetime_prints_day_month_then_hour_minute_in_clinic_time", () => {
    expect(formatDateTime("2026-09-20T02:05:00Z")).toBe("20/09 09:05");
  });

  it("a_missing_datetime_prints_a_dash", () => {
    expect(formatDateTime(null)).toBe("-");
  });
});

describe("due labels", () => {
  it("due_today_shows_the_time", () => {
    expect(dueLabel("2026-09-20T14:30:00+07:00", NOW)).toBe("Hôm nay 14:30");
  });

  it("due_tomorrow_says_tomorrow", () => {
    expect(dueLabel("2026-09-21T09:00:00+07:00", NOW)).toBe("Ngày mai 09:00");
  });

  it("due_two_days_ago_is_overdue_by_two_days", () => {
    expect(dueLabel("2026-09-18T09:00:00+07:00", NOW)).toBe("Quá hạn 2 ngày");
  });

  it("a_task_due_earlier_today_is_not_overdue", () => {
    expect(isOverdue("2026-09-20T07:00:00+07:00", NOW)).toBe(false);
  });

  it("a_task_due_yesterday_is_overdue", () => {
    expect(isOverdue("2026-09-19T23:00:00+07:00", NOW)).toBe(true);
  });
});

describe("age", () => {
  it("before_the_birthday_this_year_the_age_is_one_less", () => {
    expect(ageYears("1990-12-01", NOW)).toBe(35);
  });

  it("on_the_birthday_the_age_counts_the_new_year", () => {
    expect(ageYears("1990-09-20", NOW)).toBe(36);
  });

  it("a_missing_birth_date_has_no_age", () => {
    expect(ageYears(null, NOW)).toBeNull();
  });
});

describe("local input", () => {
  it("datetime_local_becomes_iso_with_the_clinic_offset", () => {
    expect(localInputToIso("2026-09-21T09:00")).toBe("2026-09-21T09:00:00+07:00");
  });
});
