// The fake agent's cases (`/v1/admin/cases`): three FICTIONAL ones in memory (a follow-up waiting for the silence,
// a reminder waiting for its hour, a follow-up done). "Run now" wakes a live one the way the engine does: the wake
// is written in its log and its hour becomes now; it does not run its nodes. "Send a test now" says it was sent.
import { HOUR, MIN, type Reply, type Router, isoFromNow } from "./core";

type Case = {
  id: number;
  kind: string;
  key: string;
  channel: string;
  conversation_id: string;
  goal: string;
  status: string;
  node: string;
  state: Record<string, unknown>;
  wait_for: string | null;
  wake_at: string | null;
  deadline: string | null;
  turns: number;
  proactive_sent: number;
  end_reason: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
};

type Event = {
  seq: number;
  at: string;
  kind: string;
  node: string | null;
  detail: Record<string, unknown>;
};

const LIVE = new Set(["open", "waiting"]);

function sample(id: number, fields: Partial<Case>): Case {
  return {
    id,
    kind: "follow_up",
    key: `zalo-demo:c${id}`,
    channel: "zalo-demo",
    conversation_id: `c${id}`,
    goal: "Khách quay lại hoặc nói không",
    status: "waiting",
    node: "quiet",
    state: {},
    wait_for: "clock",
    wake_at: isoFromNow(90 * MIN),
    deadline: isoFromNow(14 * 24 * HOUR),
    turns: 0,
    proactive_sent: 0,
    end_reason: null,
    created_at: isoFromNow(-30 * MIN),
    updated_at: isoFromNow(-30 * MIN),
    closed_at: null,
    ...fields,
  };
}

function seed(): { cases: Case[]; events: Map<number, Event[]> } {
  const cases = [
    sample(3, {}),
    sample(2, {
      kind: "reminder",
      node: "check",
      wake_at: isoFromNow(20 * HOUR),
      goal: "Nhắc lịch hẹn",
    }),
    sample(1, {
      status: "done",
      node: "judge",
      wait_for: null,
      wake_at: null,
      end_reason: "done: khách đã đặt lịch",
      closed_at: isoFromNow(-2 * HOUR),
    }),
  ];
  const opened = (c: Case): Event[] => [
    { seq: 1, at: c.created_at, kind: "opened", node: c.node, detail: { goal: c.goal } },
  ];
  return { cases, events: new Map(cases.map((c) => [c.id, opened(c)])) };
}

let store = seed();

const notFound: Reply = {
  status: 404,
  body: { error: { kind: "not_found", message: "no such case" } },
};

function wake(id: number): Reply {
  const found = store.cases.find((c) => c.id === id);
  if (!found) return notFound;
  if (!LIVE.has(found.status)) {
    return {
      status: 409,
      body: { error: { kind: "not_live", message: "the case is closed, or its plugin is off" } },
    };
  }
  const now = new Date().toISOString();
  const woken = {
    ...found,
    wake_at: found.status === "waiting" ? now : found.wake_at,
    updated_at: now,
  };
  const log = store.events.get(id) ?? [];
  const entry: Event = {
    seq: log.length + 1,
    at: now,
    kind: "woken",
    node: found.node,
    detail: { by: "admin", patch: [] },
  };
  store = {
    cases: store.cases.map((c) => (c.id === id ? woken : c)),
    events: new Map([...store.events, [id, [...log, entry]]]),
  };
  return { body: woken };
}

export function registerAgentCases(r: Router): void {
  r.get("/v1/admin/cases", null, (): Reply => ({ body: { cases: store.cases } }));
  r.get("/v1/admin/cases/{case_id}", null, (ctx): Reply => {
    const found = store.cases.find((c) => c.id === Number(ctx.params.case_id));
    if (!found) return notFound;
    return { body: { ...found, events: store.events.get(found.id) ?? [] } };
  });
  r.post("/v1/admin/cases/{case_id}/wake", null, (ctx): Reply => wake(Number(ctx.params.case_id)));
  r.post("/v1/admin/cases/{case_id}/try", null, (ctx): Reply => {
    const found = store.cases.find((c) => c.id === Number(ctx.params.case_id));
    if (!found) return notFound;
    if (!LIVE.has(found.status)) {
      return {
        status: 409,
        body: { error: { kind: "not_live", message: "the case is closed, or its plugin is off" } },
      };
    }
    return { body: { sent: true, why: "" } };
  });
}
