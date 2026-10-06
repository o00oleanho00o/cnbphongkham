import { describe, expect, it } from "vitest";

import {
  countdownText,
  deviceLine,
  quietBody,
  quietError,
  quietFormOf,
  secondsLeft,
} from "./notify-view";

describe("quiet hours", () => {
  it("are off when either time is missing and default to 22:00 to 06:00", () => {
    expect(quietFormOf({ quiet_start: null, quiet_end: null })).toEqual({
      enabled: false,
      start: "22:00",
      end: "06:00",
    });
    expect(quietFormOf({ quiet_start: "21:30", quiet_end: "07:00" })).toEqual({
      enabled: true,
      start: "21:30",
      end: "07:00",
    });
  });

  it("send both nulls when switched off, so the BE clears them", () => {
    expect(quietBody({ enabled: false, start: "22:00", end: "06:00" })).toEqual({
      quiet_start: null,
      quiet_end: null,
    });
    expect(quietBody({ enabled: true, start: "22:00", end: "06:00" })).toEqual({
      quiet_start: "22:00",
      quiet_end: "06:00",
    });
  });

  it("refuse two equal times only while they are on", () => {
    expect(quietError({ enabled: true, start: "22:00", end: "22:00" })).toBe(
      "Hai mốc giờ phải khác nhau.",
    );
    expect(quietError({ enabled: false, start: "22:00", end: "22:00" })).toBeNull();
    expect(quietError({ enabled: true, start: "", end: "06:00" })).not.toBeNull();
  });
});

describe("the one-time code", () => {
  it("counts down in minutes and seconds and stops at zero", () => {
    expect(countdownText(552)).toBe("09:12");
    expect(secondsLeft(10_000, 1_000)).toBe(9);
    expect(secondsLeft(10_000, 20_000)).toBe(0);
  });
});

describe("deviceLine", () => {
  it("names the platform and the day it was last seen", () => {
    expect(deviceLine({ platform: "ios", last_seen: "2026-09-20T09:00:00+07:00" })).toBe(
      "iOS · hoạt động 20/09",
    );
  });
});
