// The shared-inbox part of the mock backend (package O): who holds a conversation, the lock on a send, identities
// and roster, one-time Zalo link and quiet hours. The BE has the real tests; this keeps the mock honest enough to
// build and look at the screens: same status codes and error codes as the contract.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { resetAttempts } from "./auth";
import { conversations } from "./data/clinic";
import { roster } from "./data/ops";
import { startMockServer } from "./server";

let server: Server;
let base: string;

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

beforeEach(resetAttempts);

async function signIn(email: string): Promise<string> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password: "demo1234" }),
  });
  expect(res.status).toBe(200);
  return res.headers.get("set-cookie")?.split(";")[0] ?? "";
}

async function call(cookie: string, method: string, path: string, body?: unknown) {
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { cookie, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? (JSON.parse(text) as Record<string, unknown>) : null };
}

/** An open thread nobody holds: the test puts it back in the queue itself, so tests do not depend on each other. */
function freshQueueThread() {
  const thread = conversations.find((c) => c.status === "pending_review");
  if (!thread) throw new Error("the seed has no open thread");
  thread.assigned_user_id = null;
  thread.assigned_user_name = null;
  return thread;
}

describe("holder of a conversation (mock)", () => {
  it("claims_an_unassigned_thread_and_answers_thread_locked_to_the_next_claim", async () => {
    const mai = await signIn("cs@pema.test");
    const thu = await signIn("thu@pema.test");
    const thread = freshQueueThread();

    const claimed = await call(mai, "POST", `/api/v1/conversations/${thread.id}/claim`, {});
    const second = await call(thu, "POST", `/api/v1/conversations/${thread.id}/claim`, {});

    expect(claimed.status).toBe(200);
    expect(claimed.json?.assigned_user_name).toBe("Mai Anh");
    expect(second.status).toBe(409);
    expect((second.json?.error as { code: string }).code).toBe("thread_locked");
  });

  it("refuses_a_send_by_somebody_else_with_the_holder_name_and_lets_the_holder_send", async () => {
    const mai = await signIn("cs@pema.test");
    const thu = await signIn("thu@pema.test");
    const thread = freshQueueThread();
    await call(mai, "POST", `/api/v1/conversations/${thread.id}/claim`, {});

    const refused = await call(thu, "POST", `/api/v1/conversations/${thread.id}/messages`, {
      text: "Dạ em chào chị",
      proactive: false,
    });
    const sent = await call(mai, "POST", `/api/v1/conversations/${thread.id}/messages`, {
      text: "Dạ em chào chị",
      proactive: false,
    });

    expect(refused.status).toBe(409);
    expect((refused.json?.error as { message: string }).message).toBe(
      "Mai Anh đang trả lời — Tiếp quản?",
    );
    expect(sent.status).toBe(201);
  });

  it("needs_a_reason_to_take_over_and_then_moves_the_thread_and_writes_the_history", async () => {
    const mai = await signIn("cs@pema.test");
    const thu = await signIn("thu@pema.test");
    const thread = freshQueueThread();
    await call(mai, "POST", `/api/v1/conversations/${thread.id}/claim`, {});

    const noReason = await call(thu, "POST", `/api/v1/conversations/${thread.id}/takeover`, {
      reason: " ",
    });
    const taken = await call(thu, "POST", `/api/v1/conversations/${thread.id}/takeover`, {
      reason: "Mai Anh đang bận ca",
    });
    const history = await call(thu, "GET", `/api/v1/conversations/${thread.id}/assignments`);

    expect(noReason.status).toBe(422);
    expect(taken.json?.assigned_user_name).toBe("Đặng Minh Thư");
    expect((history.json as unknown as { kind: string }[])[0]?.kind).toBe("takeover");
  });

  it("answers_501_when_returning_to_the_care_agent_and_releases_to_the_queue_otherwise", async () => {
    const mai = await signIn("cs@pema.test");
    const thread = freshQueueThread();
    await call(mai, "POST", `/api/v1/conversations/${thread.id}/claim`, {});

    const toAgent = await call(mai, "POST", `/api/v1/conversations/${thread.id}/release`, {
      to_agent: true,
    });
    const toQueue = await call(mai, "POST", `/api/v1/conversations/${thread.id}/release`, {
      to_agent: false,
    });

    expect(toAgent.status).toBe(501);
    expect(toQueue.json?.assigned_user_id).toBeNull();
  });

  it("lets_only_a_role_with_thread_assign_hand_a_thread_to_somebody", async () => {
    const mai = await signIn("cs@pema.test");
    const owner = await signIn("owner@pema.test");
    const thread = freshQueueThread();

    const denied = await call(mai, "POST", `/api/v1/conversations/${thread.id}/assign`, {
      user_id: null,
    });
    const allowed = await call(owner, "POST", `/api/v1/conversations/${thread.id}/assign`, {
      user_id: null,
    });

    expect(denied.status).toBe(403);
    expect(allowed.status).toBe(200);
  });

  it("does_not_let_reception_claim", async () => {
    const reception = await signIn("reception@pema.test");
    const thread = freshQueueThread();

    const res = await call(reception, "POST", `/api/v1/conversations/${thread.id}/claim`, {});

    expect(res.status).toBe(403);
  });
});

describe("identities and roster (mock)", () => {
  it("lists_the_customer_identities_before_the_internal_one_and_never_a_credential", async () => {
    const mai = await signIn("cs@pema.test");

    const res = await call(mai, "GET", "/api/v1/identities");

    const rows = res.json as unknown as { id: string; purpose: string }[];
    expect(rows.map((r) => r.purpose)).toEqual(["customer", "customer", "internal"]);
    expect(JSON.stringify(rows)).not.toMatch(/token|cookie|credential|_enc/i);
  });

  it("refuses_a_minimum_gap_above_the_maximum_and_lets_the_owner_set_limits", async () => {
    const owner = await signIn("owner@pema.test");

    const bad = await call(owner, "PATCH", "/api/v1/identities/le-tan-ca-nhan", {
      send_gap_min_s: 300,
      send_gap_max_s: 240,
    });
    const good = await call(owner, "PATCH", "/api/v1/identities/le-tan-ca-nhan", { daily_cap: 7 });

    expect(bad.status).toBe(422);
    expect((good.json?.effective as { daily_cap: number }).daily_cap).toBe(7);
  });

  it("adds_edits_and_deletes_a_shift_with_the_version_check", async () => {
    const owner = await signIn("owner@pema.test");
    const mai = "00000000-0000-4000-8001-000000000004";
    const created = await call(owner, "POST", "/api/v1/roster", {
      account_id: "pema-bot",
      user_id: mai,
      start: "22:00",
      end: "06:00",
      weekdays: ["sat"],
    });
    const id = created.json?.id as string;

    const stale = await call(owner, "PATCH", `/api/v1/roster/${id}`, { end: "07:00", version: 99 });
    const edited = await call(owner, "PATCH", `/api/v1/roster/${id}`, { end: "07:00", version: 1 });
    const removed = await call(owner, "DELETE", `/api/v1/roster/${id}`);

    expect(created.status).toBe(201);
    expect(stale.status).toBe(409);
    expect(edited.json?.version).toBe(2);
    expect(removed.status).toBe(204);
    expect(roster.some((e) => e.id === id)).toBe(false);
  });

  it("refuses_a_shift_with_equal_times_and_a_roster_write_by_an_operator", async () => {
    const owner = await signIn("owner@pema.test");
    const mai = await signIn("cs@pema.test");
    const body = {
      account_id: "pema-bot",
      user_id: "00000000-0000-4000-8001-000000000004",
      start: "12:00",
      end: "12:00",
      weekdays: ["mon"],
    };

    const equal = await call(owner, "POST", "/api/v1/roster", body);
    const denied = await call(mai, "POST", "/api/v1/roster", { ...body, end: "13:00" });

    expect(equal.status).toBe(422);
    expect(denied.status).toBe(403);
  });
});

describe("notifications (mock)", () => {
  it("starts_the_link_with_a_one_time_code_naming_the_internal_account", async () => {
    const mai = await signIn("cs@pema.test");

    const started = await call(mai, "POST", "/api/v1/me/notify-zalo/link");
    const status = await call(mai, "GET", "/api/v1/me/notify-zalo");

    expect(started.json?.code).toMatch(/^PEMA-[A-Z0-9]{4}$/);
    expect(started.json?.internal_label).toBe("Pema Nội bộ");
    expect(status.json?.linked).toBe(false);
  });

  it("saves_quiet_hours_both_or_neither", async () => {
    const mai = await signIn("cs@pema.test");

    const half = await call(mai, "PUT", "/api/v1/me/notify-preferences", {
      quiet_start: "22:00",
      quiet_end: null,
    });
    const both = await call(mai, "PUT", "/api/v1/me/notify-preferences", {
      quiet_start: "21:00",
      quiet_end: "06:30",
    });

    expect(half.status).toBe(422);
    expect(both.json).toEqual({ quiet_start: "21:00", quiet_end: "06:30" });
  });

  it("lets_only_owner_and_manager_change_the_clinic_settings", async () => {
    const mai = await signIn("cs@pema.test");
    const owner = await signIn("owner@pema.test");

    const denied = await call(mai, "PUT", "/api/v1/notifications/settings", {
      bell_enabled: false,
    });
    const allowed = await call(owner, "PUT", "/api/v1/notifications/settings", {
      ack_timeout_s: 120,
    });

    expect(denied.status).toBe(403);
    expect(allowed.json?.ack_timeout_s).toBe(120);
  });
});
