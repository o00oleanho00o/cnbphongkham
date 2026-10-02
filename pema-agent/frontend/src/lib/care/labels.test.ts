import { describe, expect, it } from "vitest";

import { codeLabel, knownCodeLabel, reasonLabel, skillLabel } from "@/lib/care/labels";

describe("care labels", () => {
  it("words a transition code by its longest known prefix", () => {
    expect(codeLabel("control:auto_to_handoff_routing:agent")).toBe(
      "Agent nhờ người nhận cuộc trò chuyện",
    );
    expect(codeLabel("control:handoff_routing_to_staff:staff:1234")).toBe(
      "Nhân viên nhận cuộc trò chuyện",
    );
    expect(codeLabel("reminder_template:d3")).toBe("Nhắc lịch theo mẫu");
    expect(codeLabel("autonomy:override_set:level0")).toBe("Đặt mức tự chủ tạm thời");
  });

  it("never shows an unknown code raw", () => {
    expect(codeLabel("something:new:from:the:backend")).toBe("Hoạt động của agent");
    expect(knownCodeLabel("something:new")).toBeNull();
    expect(reasonLabel("brand_new_signal")).toBe("Lý do khác");
  });

  it("words the reasons of the handoff skill", () => {
    expect(reasonLabel("red_flag")).toBe("Dấu hiệu nguy hiểm (cờ đỏ)");
    expect(reasonLabel("asks_for_human")).toBe("Khách muốn gặp người");
  });

  it("falls back to the code itself only for a skill name", () => {
    expect(skillLabel("laser")).toBe("Laser");
    expect(skillLabel("tiem_filler")).toBe("tiem_filler");
  });
});
