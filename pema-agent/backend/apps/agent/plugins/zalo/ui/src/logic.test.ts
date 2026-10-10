import { describe, expect, it } from "vitest";

import {
  DEFAULT_ALLOWLIST,
  clampDelay,
  formOf,
  formProblem,
  oaKeysState,
  parseIds,
  patchOf,
  qrView,
  toggledIds,
  withChannel,
} from "./logic";
import type { Account } from "./types";

const ACCOUNT: Account = {
  id: "nick-1",
  label: "Nick 1",
  channel: "zalo_personal",
  enabled: true,
  allowlist: { mode: "list", user_ids: ["111", "222"] },
  group_require_mention: false,
  respond_to_groups: true,
  group_passive_listen: false,
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
      group_passive_listen: false,
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
