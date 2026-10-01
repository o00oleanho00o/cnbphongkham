// New in Pema: validation of the channel switchboard draft.
import { describe, expect, it } from "vitest";

import {
  buildFields,
  draftFromChannel,
  hasChanges,
  usageRatio,
  type ChannelDraft,
} from "@/lib/admin/channels/channel-draft";
import type { Schemas } from "@/lib/api";

const CURRENT: Schemas["ChannelSettingsOut"] = {
  channel: "zalo_personal",
  enabled: true,
  kill_switch_on: false,
  daily_cap: 10,
  proactive_sent_today: 3,
  send_window_start: "08:00",
  send_window_end: "20:00",
  min_gap_seconds: 30,
  max_gap_seconds: 120,
  requires_friend: true,
  bridge_state: "connected",
  version: 4,
};

function draftWith(change: Partial<ChannelDraft>): ChannelDraft {
  return { ...draftFromChannel(CURRENT), ...change };
}

describe("channel_draft", () => {
  it("untouched_draft_has_no_changes", () => {
    expect(hasChanges(draftFromChannel(CURRENT), CURRENT)).toBe(false);
  });

  it("only_edited_fields_are_sent", () => {
    const result = buildFields(draftWith({ dailyCap: "5", maxGap: "300" }), CURRENT);
    expect(result).toEqual({ ok: true, fields: { daily_cap: 5, max_gap_seconds: 300 } });
  });

  it("daily_cap_above_the_limit_is_refused", () => {
    const result = buildFields(draftWith({ dailyCap: "1001" }), CURRENT);
    expect(result.ok).toBe(false);
  });

  it("daily_cap_zero_is_allowed_and_means_no_proactive_message", () => {
    const result = buildFields(draftWith({ dailyCap: "0" }), CURRENT);
    expect(result).toEqual({ ok: true, fields: { daily_cap: 0 } });
  });

  it("emptying_a_value_that_is_set_is_refused_because_the_contract_cannot_clear_it", () => {
    expect(buildFields(draftWith({ dailyCap: "" }), CURRENT).ok).toBe(false);
    expect(buildFields(draftWith({ windowStart: "", windowEnd: "" }), CURRENT).ok).toBe(false);
  });

  it("empty_cap_is_fine_when_the_channel_has_none", () => {
    const noCap = { ...CURRENT, daily_cap: null };
    expect(buildFields(draftFromChannel(noCap), noCap)).toEqual({ ok: true, fields: {} });
  });

  it("min_gap_larger_than_max_gap_is_refused", () => {
    expect(buildFields(draftWith({ minGap: "200", maxGap: "100" }), CURRENT).ok).toBe(false);
  });

  it("negative_or_decimal_numbers_are_refused", () => {
    expect(buildFields(draftWith({ minGap: "-1" }), CURRENT).ok).toBe(false);
    expect(buildFields(draftWith({ maxGap: "1.5" }), CURRENT).ok).toBe(false);
  });

  it("send_window_needs_both_ends_in_hh_mm", () => {
    expect(buildFields(draftWith({ windowEnd: "" }), CURRENT).ok).toBe(false);
    expect(buildFields(draftWith({ windowEnd: "25:00" }), CURRENT).ok).toBe(false);
    expect(buildFields(draftWith({ windowEnd: "21:30" }), CURRENT)).toEqual({
      ok: true,
      fields: { send_window_end: "21:30" },
    });
  });

  it("usage_ratio_is_capped_at_one_and_absent_without_a_cap", () => {
    expect(usageRatio(3, 10)).toBeCloseTo(0.3);
    expect(usageRatio(12, 10)).toBe(1);
    expect(usageRatio(3, null)).toBeNull();
    expect(usageRatio(3, 0)).toBeNull();
  });
});
