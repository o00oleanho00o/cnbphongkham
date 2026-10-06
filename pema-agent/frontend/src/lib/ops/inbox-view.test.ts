import { describe, expect, it } from "vitest";

import {
  assignmentTitle,
  conversationCode,
  customerSeesLine,
  holderText,
  identityOf,
  inboxHref,
  isInTab,
  matchesIdentity,
  overLine,
  readInboxParams,
  tabCounts,
  takenOver,
  type InboxRow,
} from "./inbox-view";

const ME = "me";
const identity = (
  id: string,
  label: string,
  channel: "zalo_bot" | "zalo_personal" | "zalo_oa",
) => ({
  id,
  label,
  channel,
  purpose: "customer" as const,
  enabled: true,
  channel_enabled: true,
  kill_switch_on: false,
  overrides: {},
  effective: { send_gap_min_s: 0, send_gap_max_s: 0 },
});
const row = (over: Partial<InboxRow>): InboxRow =>
  ({
    id: "3f2a0000-0000-4000-8007-000000000001",
    channel: "zalo_personal",
    status: "open",
    assigned_user_id: null,
    assigned_user_name: null,
    ...over,
  }) as InboxRow;

describe("tabs", () => {
  const rows = [
    row({ id: "a" }),
    row({ id: "b", assigned_user_id: ME }),
    row({ id: "c", assigned_user_id: "lan" }),
    row({ id: "d", status: "closed" }),
  ];

  it("keeps_a_closed_thread_out_of_the_queue", () => {
    expect(rows.filter((r) => isInTab(r, "queue", ME)).map((r) => r.id)).toEqual(["a"]);
  });

  it("counts_the_three_tabs", () => {
    expect(tabCounts(rows, ME)).toEqual({ queue: 1, mine: 1, all: 4 });
  });
});

describe("the holder line", () => {
  it("says_who_holds_the_thread_in_the_words_of_the_frames", () => {
    expect(holderText(row({}), ME)).toBe("Chưa ai nhận");
    expect(holderText(row({ assigned_user_id: ME }), ME)).toBe("Bạn đang giữ");
    expect(holderText(row({ assigned_user_id: "n", assigned_user_name: "Hoàng Nam" }), ME)).toBe(
      "Hoàng Nam đang giữ",
    );
  });
});

describe("identity", () => {
  const long = identity("long", "Long", "zalo_personal");
  const bot = identity("bot", "Pema CSKH", "zalo_bot");

  it("is_found_by_account_id_when_the_row_carries_it", () => {
    expect(identityOf(row({ account_id: "bot" }), [long, bot])?.label).toBe("Pema CSKH");
  });

  it("is_found_by_channel_when_only_one_customer_identity_uses_it", () => {
    expect(identityOf(row({ channel: "zalo_personal" }), [long, bot])?.label).toBe("Long");
  });

  it("is_unknown_when_two_identities_share_the_channel", () => {
    const second = identity("long2", "Long 2", "zalo_personal");
    expect(identityOf(row({ channel: "zalo_personal" }), [long, second])).toBeNull();
  });

  it("filters_by_channel_without_an_account_id_and_by_id_with_one", () => {
    expect(matchesIdentity(row({ channel: "zalo_bot" }), "bot", [long, bot])).toBe(true);
    expect(matchesIdentity(row({ channel: "zalo_bot" }), "long", [long, bot])).toBe(false);
    expect(matchesIdentity(row({ account_id: "long" }), "long", [long, bot])).toBe(true);
    expect(matchesIdentity(row({}), "all", [long, bot])).toBe(true);
  });

  it("is_written_before_the_name_as_code_and_identity", () => {
    expect(overLine(row({ channel: "zalo_personal" }), [long])).toBe("#3F2A · Long");
    expect(overLine(row({}), [])).toBe("#3F2A");
    expect(conversationCode("3f2a0000-0000")).toBe("#3F2A");
  });

  it("is_what_the_customer_sees_instead_of_the_operator", () => {
    expect(customerSeesLine("Long")).toBe(
      'Khách thấy tin này từ "Long", không thấy tên nhân viên.',
    );
  });
});

describe("the URL", () => {
  it("round_trips_thread_tab_and_identity", () => {
    const href = inboxHref({ conversationId: "c1", tab: "mine", identityId: "long" });
    expect(href).toBe("/inbox?c=c1&tab=mine&identity=long");
    expect(readInboxParams(new URLSearchParams(href.split("?")[1]), true)).toEqual({
      conversationId: "c1",
      tab: "mine",
      identityId: "long",
    });
  });

  it("leaves_out_the_default_identity", () => {
    expect(inboxHref({ tab: "all", identityId: "all" })).toBe("/inbox?tab=all");
    expect(inboxHref({})).toBe("/inbox");
  });

  it("opens_on_the_queue_for_a_role_that_can_claim_and_on_all_for_one_that_cannot", () => {
    expect(readInboxParams(new URLSearchParams(""), true).tab).toBe("queue");
    expect(readInboxParams(new URLSearchParams(""), false).tab).toBe("all");
    expect(readInboxParams(new URLSearchParams("tab=bogus"), true).tab).toBe("queue");
  });

  it("reads_the_deep_link_of_a_notification", () => {
    expect(readInboxParams(new URLSearchParams("conversation=abc"), true).conversationId).toBe(
      "abc",
    );
  });
});

describe("takenOver", () => {
  it("names_the_new_holder_of_a_thread_I_held", () => {
    const before = new Map<string, string | null>([
      ["t1", ME],
      ["t2", ME],
      ["t3", null],
    ]);
    const after = [
      { id: "t1", assigned_user_id: "lan", assigned_user_name: "Bùi Ngọc Lan" },
      { id: "t2", assigned_user_id: ME, assigned_user_name: "Mai Anh" },
      { id: "t3", assigned_user_id: "lan", assigned_user_name: "Bùi Ngọc Lan" },
    ];
    expect(takenOver(before, after, ME)).toEqual([{ id: "t1", byName: "Bùi Ngọc Lan" }]);
  });
});

describe("assignmentTitle", () => {
  const base = { id: "e", at: "2026-09-20T09:40:00+07:00", by: "Hệ thống" };

  it("words_each_kind", () => {
    expect(
      assignmentTitle({
        ...base,
        kind: "takeover",
        user_id: "a",
        user_name: "Hoàng Nam",
        previous_user_name: "Mai Anh",
      }),
    ).toBe("Hoàng Nam tiếp quản từ Mai Anh");
    expect(assignmentTitle({ ...base, kind: "claim", user_id: "a", user_name: "Mai Anh" })).toBe(
      "Mai Anh nhận hội thoại",
    );
    expect(
      assignmentTitle({
        ...base,
        kind: "shift_end",
        user_id: null,
        previous_user_name: "Hoàng Nam",
      }),
    ).toBe("Hết ca: Hoàng Nam trả hội thoại về hàng chờ");
    expect(assignmentTitle({ ...base, kind: "assign", by: "Hà", user_id: null })).toBe(
      "Hà bỏ người phụ trách",
    );
  });
});
