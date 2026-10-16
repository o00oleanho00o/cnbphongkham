import { describe, expect, it } from "vitest";

import {
  DEFAULT_ALLOWLIST,
  accountScope,
  addableItems,
  clampDelay,
  formOf,
  formProblem,
  groupChoices,
  oaKeysState,
  ownItems,
  parseIds,
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

  it("starts a bot closed and a personal nick open", () => {
    const form = formOf(null);
    expect(form.allowlistMode).toBe("all");
    expect(withChannel(form, "zalo_bot").allowlistMode).toBe("list");
    expect(withChannel(form, "zalo_oa").allowlistMode).toBe(DEFAULT_ALLOWLIST.zalo_oa);
  });

  it("reads ids split by lines, commas and spaces, once each", () => {
    expect(parseIds(" 111\n222, 333 ;111\n\n")).toEqual(["111", "222", "333"]);
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

  it("refuses an id the server would not take, but not an empty list", () => {
    const form = { ...formOf(ACCOUNT), allowlistIds: "" };
    expect(formProblem(form, false)).toBeNull();
    expect(formProblem({ ...form, allowlistIds: "111\nbad/id" }, false)).toMatch(/bad\/id/);
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
      { id: "g1", name: "Nhóm khám", listening: false },
      { id: "g2", name: "(không tên)", listening: true },
    ]);
  });

  it("keeps_a_chosen_group_that_was_not_seen_so_it_can_be_switched_off", () => {
    expect(groupChoices(seen, ["g9"]).at(-1)).toEqual({ id: "g9", name: "g9", listening: true });
  });

  it("the_form_sends_the_chosen_groups_in_order", () => {
    const form = { ...formOf(ACCOUNT), listenGroupIds: ["g3", "g1"] };
    expect(patchOf(form).listen_group_ids).toEqual(["g1", "g3"]);
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
