import { describe, expect, it } from "vitest";

import type { PresenceViewer } from "@/lib/live/live-types";
import {
  presenceStateFor,
  presenceText,
  shortName,
  someoneReplying,
} from "@/lib/ops/presence-view";

const lan: PresenceViewer = { user_id: "u-lan", name: "Bùi Ngọc Lan", state: "viewing" };
const ha: PresenceViewer = { user_id: "u-ha", name: "Nguyễn Thanh Hà", state: "replying" };
const tam: PresenceViewer = { user_id: "u-tam", name: "BS. Lê Minh Tâm", state: "viewing" };

describe("shortName", () => {
  it("uses the given name, the last word in Vietnamese", () => {
    expect(shortName("Bùi Ngọc Lan")).toBe("Lan");
    expect(shortName("  Mai   Anh ")).toBe("Anh");
    expect(shortName("Lan")).toBe("Lan");
  });

  it("keeps a title in front of the given name", () => {
    expect(shortName("BS. Lê Minh Tâm")).toBe("BS. Tâm");
  });

  it("never returns an empty string", () => {
    expect(shortName("   ")).toBe("Một đồng nghiệp");
  });
});

describe("presenceText", () => {
  it("is null when nobody else is on the conversation", () => {
    expect(presenceText([])).toBeNull();
  });

  it("says who is viewing", () => {
    expect(presenceText([lan])).toBe("Lan đang xem");
  });

  it("says who is replying", () => {
    expect(presenceText([ha])).toBe("Hà đang trả lời");
  });

  it("puts the person replying first and groups names of the same state", () => {
    expect(presenceText([lan, ha, tam])).toBe("Hà đang trả lời · Lan, BS. Tâm đang xem");
  });

  it("does not list more than two names", () => {
    const many = ["A An", "B Bình", "C Cường", "D Dũng"].map((name, i) => ({
      user_id: `u-${i}`,
      name,
      state: "viewing" as const,
    }));
    expect(presenceText(many)).toBe("An, Bình và 2 người khác đang xem");
  });
});

describe("someoneReplying", () => {
  it("is true only when a colleague is writing a reply", () => {
    expect(someoneReplying([lan, tam])).toBe(false);
    expect(someoneReplying([lan, ha])).toBe(true);
  });
});

describe("presenceStateFor", () => {
  it("is replying as soon as there is a draft, viewing otherwise", () => {
    expect(presenceStateFor("")).toBe("viewing");
    expect(presenceStateFor("   ")).toBe("viewing");
    expect(presenceStateFor("Xin chào")).toBe("replying");
  });
});
