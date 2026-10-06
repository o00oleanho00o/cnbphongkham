import { describe, expect, it } from "vitest";

import {
  ackTimeoutText,
  formOf,
  limitsText,
  notifierFacts,
  onDutyText,
  parseLimit,
  updateBody,
  validateForm,
} from "./identity-view";

const identity = {
  id: "le-tan",
  label: "Long",
  channel: "zalo_personal" as const,
  purpose: "customer" as const,
  enabled: true,
  channel_enabled: true,
  kill_switch_on: false,
  overrides: { daily_cap: null, send_gap_min_s: null, send_gap_max_s: null },
  effective: { daily_cap: 5, send_gap_min_s: 60, send_gap_max_s: 240 },
};

describe("limitsText", () => {
  it("says the limits come from the channel when there is no override", () => {
    expect(limitsText(identity)).toBe(
      "tối đa 5 tin chủ động/ngày · cách nhau 60–240 giây (theo kênh)",
    );
  });

  it("says riêng when the identity overrides one of them", () => {
    const own = { ...identity, overrides: { ...identity.overrides, daily_cap: 10 } };
    expect(limitsText({ ...own, effective: { ...own.effective, daily_cap: 10 } })).toContain(
      "(riêng)",
    );
  });

  it("says there is no daily cap when the channel has none", () => {
    const open = { ...identity, effective: { ...identity.effective, daily_cap: null } };
    expect(limitsText(open)).toContain("không giới hạn tin chủ động/ngày");
  });
});

describe("the identity form", () => {
  it("starts from the overrides, blank where the channel applies", () => {
    expect(formOf(identity)).toEqual({
      label: "Long",
      purpose: "customer",
      dailyCap: "",
      gapMin: "",
      gapMax: "",
    });
  });

  it("clears an override when its box is blank and keeps a number", () => {
    expect(parseLimit("", 1000)).toBeNull();
    expect(parseLimit(" 12 ", 1000)).toBe(12);
    expect(parseLimit("1001", 1000)).toBeUndefined();
    expect(parseLimit("-1", 1000)).toBeUndefined();
    expect(parseLimit("1.5", 1000)).toBeUndefined();
  });

  it("refuses a minimum gap above the maximum, as the frame WM27 shows", () => {
    const errors = validateForm({ ...formOf(identity), gapMin: "300", gapMax: "240" });
    expect(errors.gapMin).toBe("Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa.");
  });

  it("refuses an empty name and builds the PATCH body with nulls for blank limits", () => {
    expect(validateForm({ ...formOf(identity), label: "  " }).label).toBeDefined();
    expect(updateBody({ ...formOf(identity), label: " Long ", dailyCap: "7" })).toEqual({
      label: "Long",
      purpose: "customer",
      daily_cap: 7,
      send_gap_min_s: null,
      send_gap_max_s: null,
    });
  });
});

describe("on duty and the notifier", () => {
  it("lists the operators on duty, or null", () => {
    expect(onDutyText([])).toBeNull();
    expect(onDutyText([{ name: "Hoàng Nam" }, { name: "Mai Anh" }])).toBe("Hoàng Nam, Mai Anh");
  });

  it("words the notifier settings", () => {
    const settings = {
      ack_timeout_s: 180,
      bell_enabled: true,
      group_enabled: true,
      in_app_enabled: true,
      push_enabled: false,
      team_group_id: "g1",
    };
    expect(notifierFacts({ label: "Pema Nội bộ" }, settings)).toEqual([
      ["Tài khoản", "Pema Nội bộ"],
      ["Chuông Zalo cho nhân viên", "Bật"],
      ["Nhóm Zalo của đội", "Đã đặt"],
      ["Chờ xác nhận trước khi gọi qua Zalo", "3 phút"],
    ]);
    expect(ackTimeoutText(90)).toBe("90 giây");
  });
});
