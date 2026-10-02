import { describe, expect, it } from "vitest";

import type { Shift } from "@/lib/care/care-types";
import {
  addInterval,
  changeInterval,
  declineError,
  instructionError,
  onCallErrors,
  parseBounded,
  parseDays,
  parseSkills,
  releaseBody,
  releaseError,
  removeInterval,
  shiftError,
} from "@/lib/care/forms";

const EMPTY: Shift = { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] };

describe("decline and instruction", () => {
  it("asks for a reason and an instruction", () => {
    expect(declineError("  ")).toBe("Hãy ghi lý do từ chối.");
    expect(declineError("Đang bận ca khác")).toBe("");
    expect(declineError("x".repeat(501))).toContain("tối đa 500");
    expect(instructionError("")).toBe("Hãy nhập nội dung cần nói với agent.");
    expect(instructionError("Gọi khách bằng chị")).toBe("");
  });
});

describe("release form", () => {
  it("needs nothing to keep the level", () => {
    expect(releaseError({ note: "", level: "", days: "" }, 30)).toBe("");
    expect(releaseBody({ note: " ghi chú ", level: "", days: "7" })).toEqual({
      note: "ghi chú",
      level: null,
      days: null,
    });
  });

  it("needs a number of days within the limit when a level is chosen", () => {
    expect(releaseError({ note: "", level: "L0", days: "" }, 30)).toBe(
      "Hãy nhập số ngày áp dụng mức đã chọn.",
    );
    expect(releaseError({ note: "", level: "L0", days: "45" }, 30)).toBe("Số ngày từ 1 đến 30.");
    expect(releaseError({ note: "", level: "L0", days: "0" }, 30)).toBe("Số ngày từ 1 đến 30.");
    expect(releaseError({ note: "", level: "L0", days: "7" }, 30)).toBe("");
    expect(releaseBody({ note: "", level: "L1", days: "7" })).toEqual({
      note: "",
      level: "L1",
      days: 7,
    });
  });

  it("reads whole numbers only", () => {
    expect(parseDays("12")).toBe(12);
    expect(parseDays("1.5")).toBeNull();
    expect(parseDays("abc")).toBeNull();
  });
});

describe("on-call and shifts", () => {
  it("checks the number and the owner", () => {
    expect(onCallErrors({ zalo_number: "0000000001", owner: "Trực đêm" })).toEqual({
      number: "",
      owner: "",
    });
    expect(onCallErrors({ zalo_number: "12ab", owner: " " }).number).not.toBe("");
    expect(onCallErrors({ zalo_number: "0000000001", owner: " " }).owner).not.toBe("");
  });

  it("adds, changes and removes an interval without touching the original", () => {
    const added = addInterval(EMPTY, "mon");
    expect(EMPTY.mon).toHaveLength(0);
    expect(added.mon).toEqual([{ start: "08:00", end: "17:00" }]);
    const changed = changeInterval(added, "mon", 0, { end: "12:00" });
    expect(changed.mon[0]?.end).toBe("12:00");
    expect(added.mon[0]?.end).toBe("17:00");
    expect(removeInterval(changed, "mon", 0).mon).toHaveLength(0);
  });

  it("rejects a bad time or an empty interval", () => {
    expect(shiftError(EMPTY)).toBe("");
    expect(shiftError({ ...EMPTY, tue: [{ start: "8am", end: "17:00" }] })).toBe(
      "Giờ theo dạng 08:00.",
    );
    expect(shiftError({ ...EMPTY, tue: [{ start: "08:00", end: "08:00" }] })).toContain(
      "không được trùng",
    );
    expect(shiftError({ ...EMPTY, tue: [{ start: "22:00", end: "06:00" }] })).toBe("");
  });
});

describe("parsers", () => {
  it("splits skills and keeps each once", () => {
    expect(parseSkills("Laser, mun  laser;nam")).toEqual(["laser", "mun", "nam"]);
  });

  it("bounds numbers and accepts a decimal comma", () => {
    expect(parseBounded("0,85", 0, 1)).toBe(0.85);
    expect(parseBounded("1.2", 0, 1)).toBeNull();
    expect(parseBounded("", 0, 1)).toBeNull();
    expect(parseBounded("abc", 0, 1)).toBeNull();
  });
});
