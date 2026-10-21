import { describe, expect, it } from "vitest";

import {
  DEFAULT_ALLOWLIST,
  accountScope,
  addableItems,
  clampDelay,
  formOf,
  formProblem,
  groupChoices,
  personChoices,
  shownChoices,
  oaKeysState,
  ownItems,
  patchOf,
  qrView,
  sharedItems,
  toggledIds,
  withAccount,
  withChannel,
  withoutAccount,
} from "./logic";
import type { Account, SkillEffective, SkillItem } from "./types";

const ACCOUNT: Account = {
  id: "nick-1",
  label: "Nick 1",
  channel: "zalo_personal",
  enabled: true,
  allowlist: { mode: "list", user_ids: ["111", "222"] },
  group_allowlist: { mode: "list", group_ids: ["g1", "g2"] },
  group_require_mention: false,
  respond_to_groups: true,
  listen_group_ids: ["g1"],
  auto_react_enabled: true,
  auto_react_icon: "like",
  typing_indicator_enabled: false,
  disabled_tools: ["web_search"],
  auto_accept_friends: true,
  auto_accept_friend_delay_minutes: 5,
  running: true,
  has_credentials: true,
  warning: null,
};

describe("account form", () => {
  it("round-trips an account into the same update", () => {
    expect(patchOf(formOf(ACCOUNT))).toEqual({
      label: "Nick 1",
      allowlist: { mode: "list", user_ids: ["111", "222"] },
      group_allowlist: { mode: "list", group_ids: ["g1", "g2"] },
      respond_to_groups: true,
      group_require_mention: false,
      listen_group_ids: ["g1"],
      typing_indicator_enabled: false,
      auto_react_enabled: true,
      auto_react_icon: "like",
      auto_accept_friends: true,
      auto_accept_friend_delay_minutes: 5,
      disabled_tools: ["web_search"],
    });
  });

  it("keeps the people list and the group list apart", () => {
    const form = { ...formOf(ACCOUNT), groupAllowlistMode: "all" as const, groupAllowlistIds: ["g9", "g3"] };

    expect(patchOf(form).allowlist).toEqual({ mode: "list", user_ids: ["111", "222"] });
    expect(patchOf(form).group_allowlist).toEqual({ mode: "all", group_ids: ["g3", "g9"] });
  });

  it("starts a bot closed for groups too and a personal nick open", () => {
    const form = formOf(null);
    expect(form.allowlistMode).toBe("all");
    expect(withChannel(form, "zalo_bot").allowlistMode).toBe("list");
    expect(withChannel(form, "zalo_oa").allowlistMode).toBe(DEFAULT_ALLOWLIST.zalo_oa);
  });

  it("checks the id only when creating, and the label always", () => {
    const form = { ...formOf(null), label: "Nick", riskAccepted: true };
    expect(formProblem({ ...form, id: "Nick 1" }, true)).toMatch(/ID/);
    expect(formProblem({ ...form, id: "x".repeat(59) }, true)).toMatch(/58/);
    expect(formProblem({ ...form, id: "nick-1" }, true)).toBeNull();
    expect(formProblem({ ...form, id: "" }, false)).toBeNull();
    expect(formProblem({ ...form, label: "  " }, false)).toMatch(/tên/);
  });

  it("asks a new personal nick to accept the risk, but not a bot or a saved nick", () => {
    const form = { ...formOf(null), id: "nick-1", label: "Nick" };
    expect(formProblem(form, true)).toMatch(/rủi ro/);
    expect(formProblem({ ...form, channel: "zalo_bot" }, true)).toBeNull();
    expect(formProblem(form, false)).toBeNull();
  });

  it("sends the chosen people in order, and none when none is chosen", () => {
    const form = { ...formOf(ACCOUNT), allowlistUserIds: ["222", "111"] };
    expect(patchOf(form).allowlist).toEqual({ mode: "list", user_ids: ["111", "222"] });
    expect(patchOf({ ...form, allowlistUserIds: [] }).allowlist?.user_ids).toEqual([]);
    expect(formProblem({ ...form, allowlistUserIds: [] }, false)).toBeNull();
  });

  it("keeps the friend delay a whole number of minutes in range", () => {
    expect(clampDelay(2.6)).toBe(3);
    expect(clampDelay(-4)).toBe(0);
    expect(clampDelay(99999)).toBe(1440);
    expect(clampDelay(Number.NaN)).toBe(0);
  });
});

describe("recipients", () => {
  it("lets one user in or out without touching the others", () => {
    expect(toggledIds(["1", "2"], "3", true)).toEqual(["1", "2", "3"]);
    expect(toggledIds(["1", "2"], "2", true)).toEqual(["1", "2"]);
    expect(toggledIds(["1", "2"], "1", false)).toEqual(["2"]);
  });
});

describe("groups to listen to", () => {
  const seen = [
    { account_id: "nick-1", thread_id: "g1", name: "Nhóm khám" },
    { account_id: "nick-1", thread_id: "g2", name: "" },
  ];

  it("offers_every_seen_group_with_its_choice_and_a_name_for_the_unnamed", () => {
    expect(groupChoices(seen, ["g2"])).toEqual([
      { id: "g1", name: "Nhóm khám", on: false },
      { id: "g2", name: "(không tên)", on: true },
    ]);
  });

  it("keeps_a_chosen_group_that_was_not_seen_so_it_can_be_switched_off", () => {
    expect(groupChoices(seen, ["g9"]).at(-1)).toEqual({ id: "g9", name: "g9", on: true });
  });

  it("the_form_sends_the_chosen_groups_in_order", () => {
    const form = { ...formOf(ACCOUNT), listenGroupIds: ["g3", "g1"] };
    expect(patchOf(form).listen_group_ids).toEqual(["g1", "g3"]);
  });
});

describe("people to answer", () => {
  const seen = [
    { account_id: "nick-1", user_id: "111", display_name: "Lan", first_seen: "", last_seen: "", message_count: 3 },
    { account_id: "nick-1", user_id: "222", display_name: "", first_seen: "", last_seen: "", message_count: 1 },
  ];

  it("offers_every_person_who_wrote_off_unless_chosen", () => {
    expect(personChoices(seen, ["222"])).toEqual([
      { id: "111", name: "Lan", on: false },
      { id: "222", name: "(không tên)", on: true },
    ]);
  });

  it("keeps_a_listed_person_who_has_not_written_so_the_list_can_be_cleaned", () => {
    expect(personChoices(seen, ["999"]).at(-1)).toEqual({ id: "999", name: "999", on: true });
  });
});

describe("people from friends", () => {
  const wrote = [
    { account_id: "nick-1", user_id: "111", display_name: "Lan", first_seen: "", last_seen: "", message_count: 3 },
  ];
  const friends = [
    { user_id: "111", display_name: "Lan (bạn)", avatar_url: null },
    { user_id: "333", display_name: "Minh", avatar_url: null },
    { user_id: "444", display_name: "", avatar_url: null },
  ];

  it("adds_friends_who_have_not_written_after_the_ones_who_did_and_lists_nobody_twice", () => {
    expect(personChoices(wrote, ["333"], friends)).toEqual([
      { id: "111", name: "Lan", on: false },
      { id: "333", name: "Minh", on: true },
      { id: "444", name: "(không tên)", on: false },
    ]);
  });
});

describe("shown choices", () => {
  const many = [
    ...Array.from({ length: 5 }, (_, i) => ({ id: `off${i}`, name: `Khách ${i}`, on: false })),
    { id: "late", name: "Người cuối", on: true },
  ];

  it("keeps_every_switch_that_is_on_and_caps_the_ones_that_are_off_without_reordering", () => {
    const { shown, hidden } = shownChoices(many, "", 2);
    expect(shown.map((c) => c.id)).toEqual(["off0", "off1", "late"]);
    expect(hidden).toBe(3);
  });

  it("matches_the_name_or_the_id_ignoring_case_and_hides_nothing_when_all_fit", () => {
    expect(shownChoices(many, "KHÁCH 3").shown.map((c) => c.id)).toEqual(["off3"]);
    expect(shownChoices(many, "off4").shown.map((c) => c.id)).toEqual(["off4"]);
    expect(shownChoices(many, "").hidden).toBe(0);
  });
});

describe("oa keys", () => {
  it("goes all four or none", () => {
    const empty = { app_id: "", app_secret: "", oa_secret_key: "", refresh_token: "" };
    expect(oaKeysState(empty)).toBe("empty");
    expect(oaKeysState({ ...empty, app_id: "1" })).toBe("partial");
    expect(oaKeysState({ app_id: "1", app_secret: "s", oa_secret_key: "k", refresh_token: "r" })).toBe("complete");
  });
});

describe("qr login", () => {
  it("shows the image only while waiting for a scan", () => {
    expect(qrView({ state: "waiting_scan", qr_png_base64: "AAA", detail: null })).toEqual({
      state: "waiting_scan",
      image: "data:image/png;base64,AAA",
      error: null,
      done: false,
    });
    expect(qrView({ state: "scanned", qr_png_base64: "AAA", detail: null }).image).toBeNull();
  });

  it("stops polling at success, expiry and error, with the reason", () => {
    expect(qrView({ state: "success", qr_png_base64: null, detail: null }).done).toBe(true);
    expect(qrView({ state: "expired", qr_png_base64: null, detail: null }).done).toBe(true);
    expect(qrView({ state: "error", qr_png_base64: null, detail: "Đã từ chối" })).toMatchObject({
      done: true,
      error: "Đã từ chối",
    });
    expect(qrView({ state: "idle", qr_png_base64: null, detail: null }).done).toBe(false);
  });
});

describe("skills of one account", () => {
  const item = (id: string, scopes: string[], status: SkillItem["status"] = "active"): SkillItem => ({
    id,
    kind: "skill",
    name: id,
    description: "d",
    status,
    scopes,
  });
  const mine = accountScope("nick-1");
  const items = [
    item("a", [mine]),
    item("b", [mine, "plugin:zalo"]),
    item("c", ["channel:zalo-other"]),
    item("d", ["plugin:zalo"]),
    item("e", []),
    item("f", [mine], "archived"),
    item("g", ["channel:zalo-other"], "draft"),
    item("h", ["channel:zalo-other"], "archived"),
  ];
  const effective: SkillEffective = {
    text: null,
    items: [
      { id: "e", kind: "skill", name: "e", rank: 0, scopes: [] },
      { id: "d", kind: "skill", name: "d", rank: 1, scopes: ["plugin:zalo"] },
      { id: "b", kind: "skill", name: "b", rank: 1, scopes: [mine, "plugin:zalo"] },
      { id: "a", kind: "skill", name: "a", rank: 2, scopes: [mine] },
    ],
  };

  it("names the channel of an account the way the Zalo plugin does", () => {
    expect(mine).toBe("channel:zalo-nick-1");
  });

  it("lists the items bound to the account, not the archived ones", () => {
    expect(ownItems(items, "nick-1").map((i) => i.id)).toEqual(["a", "b"]);
  });

  it("lists the items that reach it from a wider place", () => {
    expect(sharedItems(effective).map((i) => i.id)).toEqual(["e", "d", "b"]);
  });

  it("offers only what does not reach the account yet, never an archived item", () => {
    expect(addableItems(items, effective, "nick-1").map((i) => i.id)).toEqual(["c", "g"]);
  });

  it("binds an item to the account next to its other places, and takes it away again", () => {
    expect(withAccount(items[2]!, "nick-1")).toEqual(["channel:zalo-other", mine]);
    expect(withoutAccount(items[1]!, "nick-1")).toEqual(["plugin:zalo"]);
  });

  it("refuses to take away the last place, which would widen the item to the whole agent", () => {
    expect(withoutAccount(items[0]!, "nick-1")).toBeNull();
  });
});
