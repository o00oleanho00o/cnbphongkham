import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import {
  BLOCK_FORM_PROBLEM,
  CODE_FORM_PROBLEM,
  PROTOCOL_FORM_PROBLEM,
  RATE_FORM_PROBLEM,
  SERVICE_FORM_PROBLEM,
  bpToPercentText,
  breakLabel,
  buildServiceUpdate,
  catalogErrorMessage,
  catalogStale,
  emptyProtocolForm,
  emptyServiceForm,
  formFromProtocol,
  formFromService,
  formatRate,
  formatVnd,
  loadLine,
  loadPercent,
  milestonesLabel,
  parseProtocolForm,
  parseServiceForm,
  percentTextToBp,
  serviceDetails,
  shiftLabel,
  startsNewVersion,
  studioMetadata,
  validateBlockForm,
  type ProtocolRow,
  type ServiceRow,
} from "./catalog-view";

const SERVICE: ServiceRow = {
  id: "s1",
  code: "laser-co2",
  name: "Laser theo chỉ định",
  active: true,
  protocol_code: "laser-co2",
  room_ids: ["r1", "r2"],
  price_vnd: 2_500_000,
  rate_bp: 2000,
  basis: "net",
  duration_min: 45,
  buffer_min: 15,
  terms_version: 1,
  version: 3,
};

const PROTOCOL: ProtocolRow = {
  id: "p1",
  code: "laser-co2",
  name: "Laser CO2",
  milestones: [
    { rule_key: "d7", day: 7 },
    { rule_key: "d1", day: 1 },
    { rule_key: "d3", day: 3 },
  ],
  followup_days: 30,
  window_days: 45,
  active: true,
  version: 2,
};

function parsed(form = formFromService(SERVICE), create = false, withRate = true) {
  const result = parseServiceForm(form, { create, withRate });
  if (!result.ok) throw new Error(result.problem);
  return result.value;
}

describe("money and rates", () => {
  it("writes VND with the vi-VN grouping", () => {
    expect(formatVnd(2_500_000).replace(/\s/g, " ")).toBe("2.500.000 ₫");
    expect(formatVnd(0).replace(/\s/g, " ")).toBe("0 ₫");
  });

  it("shows a rate as the percentage people type", () => {
    expect(formatRate(2000)).toBe("20%");
    expect(formatRate(1250)).toBe("12,5%");
    expect(bpToPercentText(1000)).toBe("10");
  });

  it("reads a typed percentage into basis points", () => {
    expect(percentTextToBp("20")).toBe(2000);
    expect(percentTextToBp("12,5")).toBe(1250);
    expect(percentTextToBp("12.25")).toBe(1225);
    expect(percentTextToBp("100")).toBe(10000);
    expect(percentTextToBp("0")).toBe(0);
  });

  it("refuses a rate above 100, with more decimals, negative or not a number", () => {
    expect(percentTextToBp("100,5")).toBeNull();
    expect(percentTextToBp("12,345")).toBeNull();
    expect(percentTextToBp("-1")).toBeNull();
    expect(percentTextToBp("abc")).toBeNull();
    expect(percentTextToBp("")).toBeNull();
  });
});

describe("service form", () => {
  it("accepts the bounds of the old web: 15-180 minutes, buffer 0-60, price not negative", () => {
    const base = formFromService(SERVICE);
    expect(
      parseServiceForm(
        { ...base, duration: "15", buffer: "0", price: "0" },
        { create: false, withRate: true },
      ).ok,
    ).toBe(true);
    expect(
      parseServiceForm(
        { ...base, duration: "180", buffer: "60" },
        { create: false, withRate: true },
      ).ok,
    ).toBe(true);
  });

  it("tells the same sentence as the old web for a bad name, duration, buffer or price", () => {
    const base = formFromService(SERVICE);
    for (const patch of [
      { name: "  " },
      { duration: "14" },
      { duration: "181" },
      { buffer: "61" },
      { buffer: "-1" },
      { price: "-5" },
      { price: "12,5" },
      { price: "" },
    ]) {
      const result = parseServiceForm({ ...base, ...patch }, { create: false, withRate: true });
      expect(result).toEqual({ ok: false, problem: SERVICE_FORM_PROBLEM });
    }
  });

  it("checks the code only when a service is created", () => {
    const form = { ...emptyServiceForm(), name: "Mới", price: "1000", code: "Bad Code" };
    expect(parseServiceForm(form, { create: true, withRate: true })).toEqual({
      ok: false,
      problem: CODE_FORM_PROBLEM,
    });
    expect(
      parseServiceForm({ ...form, code: "peel-light" }, { create: true, withRate: true }).ok,
    ).toBe(true);
    expect(parseServiceForm(form, { create: false, withRate: true }).ok).toBe(true);
  });

  it("checks the rate only for someone who sees the commission terms", () => {
    const form = { ...formFromService(SERVICE), rate: "150" };
    expect(parseServiceForm(form, { create: false, withRate: true })).toEqual({
      ok: false,
      problem: RATE_FORM_PROBLEM,
    });
    expect(parseServiceForm(form, { create: false, withRate: false }).ok).toBe(true);
  });

  it("sends only what changed and the version that was read", () => {
    const same = buildServiceUpdate(SERVICE, parsed(), true);
    expect(same).toBeNull();
    const body = buildServiceUpdate(
      SERVICE,
      parsed({ ...formFromService(SERVICE), price: "2600000", name: "Tên khác" }),
      true,
    );
    expect(body).toEqual({ version: 3, price_vnd: 2_600_000, name: "Tên khác" });
  });

  it("treats the same rooms in another order as no change and detaches a protocol with null", () => {
    const form = { ...formFromService(SERVICE), roomIds: ["r2", "r1"], protocolCode: "" };
    expect(buildServiceUpdate(SERVICE, parsed(form), true)).toEqual({
      version: 3,
      protocol_code: null,
    });
  });

  it("never sends the commission terms for someone who does not see them", () => {
    const hidden: ServiceRow = { ...SERVICE, rate_bp: null, basis: null };
    const form = { ...formFromService(hidden), price: "1" };
    const body = buildServiceUpdate(hidden, parsed(form, false, false), false);
    expect(body).toEqual({ version: 3, price_vnd: 1 });
  });

  it("says when a save starts a new price snapshot", () => {
    expect(startsNewVersion({ version: 1, price_vnd: 5 })).toBe(true);
    expect(startsNewVersion({ version: 1, rate_bp: 5 })).toBe(true);
    expect(startsNewVersion({ version: 1, duration_min: 30 })).toBe(true);
    expect(startsNewVersion({ version: 1, name: "x", active: false, room_ids: [] })).toBe(false);
  });

  it("lists duration and buffer, leaving the buffer out when there is none", () => {
    expect(serviceDetails({ duration_min: 45, buffer_min: 15 })).toEqual([
      "45 phút điều trị",
      "15 phút chuẩn bị phòng",
    ]);
    expect(serviceDetails({ duration_min: 30, buffer_min: 0 })).toEqual(["30 phút điều trị"]);
  });
});

describe("protocols", () => {
  it("words the milestones in day order", () => {
    expect(milestonesLabel(PROTOCOL)).toBe("D+1, D+3, D+7");
    expect(milestonesLabel({ milestones: [] })).toBe("Không có mốc");
  });

  it("round-trips the laser-co2 protocol through the form", () => {
    const form = formFromProtocol(PROTOCOL);
    expect(form.milestones).toEqual({ d1: "1", d3: "3", d7: "7" });
    const result = parseProtocolForm(form, { create: false });
    expect(result).toEqual({
      ok: true,
      value: {
        name: "Laser CO2",
        milestones: [
          { rule_key: "d1", day: 1 },
          { rule_key: "d3", day: 3 },
          { rule_key: "d7", day: 7 },
        ],
        followupDays: 30,
        windowDays: 45,
        active: true,
      },
    });
  });

  it("an empty milestone or review box means the protocol has none", () => {
    const form = {
      ...formFromProtocol(PROTOCOL),
      milestones: { d1: "1", d3: "", d7: "" },
      followup: "",
    };
    const result = parseProtocolForm(form, { create: false });
    expect(result.ok && result.value.milestones).toEqual([{ rule_key: "d1", day: 1 }]);
    expect(result.ok && result.value.followupDays).toBeNull();
  });

  it("refuses a milestone beyond the window, a bad day or a bad review day", () => {
    const base = formFromProtocol(PROTOCOL);
    for (const patch of [
      { milestones: { d1: "1", d3: "3", d7: "60" } },
      { milestones: { d1: "x", d3: "3", d7: "7" } },
      { followup: "0" },
      { followup: "366" },
      { window: "0" },
      { name: " " },
    ]) {
      expect(parseProtocolForm({ ...base, ...patch }, { create: false })).toEqual({
        ok: false,
        problem: PROTOCOL_FORM_PROBLEM,
      });
    }
  });

  it("checks the code of a new protocol", () => {
    expect(
      parseProtocolForm({ ...emptyProtocolForm(), name: "Peel", code: "X" }, { create: true }),
    ).toEqual({
      ok: false,
      problem: CODE_FORM_PROBLEM,
    });
    expect(
      parseProtocolForm({ ...emptyProtocolForm(), name: "Peel", code: "peel-5" }, { create: true })
        .ok,
    ).toBe(true);
  });
});

describe("doctors, rooms and blocks", () => {
  const SHIFT = [
    { start: "08:00", end: "12:00" },
    { start: "13:00", end: "18:00" },
  ];

  it("writes the shift of the day and the break between its intervals", () => {
    expect(shiftLabel(SHIFT)).toBe("08:00–12:00 · 13:00–18:00");
    expect(breakLabel(SHIFT)).toBe("Nghỉ 12:00–13:00");
    expect(shiftLabel([])).toBe("Chưa có ca");
    expect(breakLabel([{ start: "08:00", end: "18:00" }])).toBeNull();
    expect(breakLabel([])).toBeNull();
  });

  it("measures the load of the day against the shift", () => {
    expect(loadPercent(270, 540)).toBe(50);
    expect(loadPercent(900, 540)).toBe(100);
    expect(loadPercent(30, 0)).toBe(0);
    expect(loadLine({ booked_count: 6, booked_minutes: 270, shift_minutes: 540 })).toBe(
      "6 lịch · 270 phút điều trị / 540 phút ca",
    );
  });

  it("accepts a block inside 08:00-18:00 with a reason and a room", () => {
    const ok = {
      roomId: "r1",
      day: "2026-09-21",
      start: "09:00",
      end: "10:30",
      reason: "Vệ sinh phòng",
    };
    expect(validateBlockForm(ok)).toBe("");
    for (const patch of [
      { start: "07:30" },
      { end: "18:30" },
      { start: "10:30", end: "09:00" },
      { start: "09:00", end: "09:00" },
      { reason: "  " },
      { roomId: "" },
      { day: "" },
    ]) {
      expect(validateBlockForm({ ...ok, ...patch })).toBe(BLOCK_FORM_PROBLEM);
    }
  });
});

describe("studio text", () => {
  it("says what the photos are and whether consent is on record", () => {
    expect(studioMetadata("Chính diện", true, false)).toBe(
      "Metadata: vùng Mặt; góc Chính diện; mốc buổi minh họa; đồng ý chăm sóc: có ghi nhận.",
    );
    expect(studioMetadata("Má trái", false, true)).toContain("chưa xác nhận");
  });
});

describe("error sentences", () => {
  it("uses the backend's own sentence for a refused value and a fixed one for access and conflicts", () => {
    expect(
      catalogErrorMessage(new ApiError(422, "Mã dịch vụ đã tồn tại.", "validation_failed")),
    ).toBe("Mã dịch vụ đã tồn tại.");
    expect(catalogErrorMessage(new ApiError(409, "x", "version_conflict"))).toContain(
      "vừa được người khác thay đổi",
    );
    expect(catalogErrorMessage(new ApiError(403, "x", "forbidden"))).toContain(
      "chủ phòng khám và quản lý",
    );
    expect(catalogErrorMessage(new ApiError(500, "boom"))).toBe("Có lỗi xảy ra. Hãy thử lại.");
    expect(catalogErrorMessage(new Error("x"))).toBe("Có lỗi xảy ra. Hãy thử lại.");
  });

  it("reloads the list after a conflict or a missing row only", () => {
    expect(catalogStale(new ApiError(409, "x", "version_conflict"))).toBe(true);
    expect(catalogStale(new ApiError(404, "x", "not_found"))).toBe(true);
    expect(catalogStale(new ApiError(422, "x", "validation_failed"))).toBe(false);
    expect(catalogStale(new Error("x"))).toBe(false);
  });
});
