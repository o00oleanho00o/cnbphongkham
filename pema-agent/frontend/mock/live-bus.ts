// Mock of the "several people at once" backend: the event bus behind `GET /api/v1/events` (SSE), the presence
// table behind `POST /api/v1/conversations/{id}/presence` and `viewers`, and a simulator that sends an event
// every now and then while somebody listens, so the screens can be seen reacting without a second person.
//
// Events say WHAT changed (type + object id), never the content. Presence lives in memory and expires after
// PRESENCE_TTL_MS without a beat (the real beat is every 15 seconds).
import { EventEmitter } from "node:events";

import { USERS } from "./auth";

export type LiveEventType =
  | "inbox.changed"
  | "tasks.changed"
  | "review.changed"
  | "presence.changed"
  | "handoff.changed"
  | "appointments.changed"
  | "care.changed";
export type LiveMessage = { type: LiveEventType; id: string | null };
export type PresenceState = "viewing" | "replying";
export type Viewer = { user_id: string; name: string; state: PresenceState };

export const PRESENCE_TTL_MS = 40_000;
const SIMULATE_ROTATION: readonly LiveEventType[] = [
  "inbox.changed",
  "tasks.changed",
  "appointments.changed",
  "review.changed",
  "handoff.changed",
];

const bus = new EventEmitter();
bus.setMaxListeners(0);

export function emitLive(type: LiveEventType, id: string | null): void {
  const message: LiveMessage = { type, id };
  bus.emit("event", message);
}

let simulator: ReturnType<typeof setInterval> | null = null;
let simulated = 0;

function simulatorPeriodMs(): number {
  const fromEnv = Number.parseInt(process.env.MOCK_LIVE_PERIOD_MS ?? "", 10);
  return Number.isNaN(fromEnv) ? 20_000 : fromEnv;
}

function startSimulator(): void {
  const period = simulatorPeriodMs();
  if (simulator || period <= 0) return;
  simulator = setInterval(() => {
    const type = SIMULATE_ROTATION[simulated % SIMULATE_ROTATION.length] ?? "inbox.changed";
    simulated += 1;
    emitLive(type, null);
  }, period);
  simulator.unref();
}

function stopSimulatorWhenAlone(): void {
  if (bus.listenerCount("event") > 0 || !simulator) return;
  clearInterval(simulator);
  simulator = null;
}

/** One SSE client. Returns the way to stop listening. */
export function subscribe(listener: (message: LiveMessage) => void): () => void {
  bus.on("event", listener);
  startSimulator();
  return () => {
    bus.off("event", listener);
    stopSimulatorWhenAlone();
  };
}

type Beat = { name: string; state: PresenceState; expiresAt: number };
const presence = new Map<string, Map<string, Beat>>();

/** Record "this user is on this conversation". True when what colleagues see changed. */
export function touchPresence(
  conversationId: string,
  userId: string,
  state: PresenceState,
): boolean {
  const now = Date.now();
  const people = presence.get(conversationId) ?? new Map<string, Beat>();
  const before = people.get(userId);
  const name = USERS.find((u) => u.id === userId)?.display_name ?? "Đồng nghiệp";
  people.set(userId, { name, state, expiresAt: now + PRESENCE_TTL_MS });
  presence.set(conversationId, people);
  const changed = !before || before.expiresAt <= now || before.state !== state;
  // An expired beat removes the person from `viewers`; tell the screens to look again then.
  setTimeout(() => emitLive("presence.changed", conversationId), PRESENCE_TTL_MS + 500).unref();
  return changed;
}

/** Remove "this user is on this conversation" at once. True when they were listed. */
export function leavePresence(conversationId: string, userId: string): boolean {
  const people = presence.get(conversationId);
  const beat = people?.get(userId);
  if (!people || !beat) return false;
  people.delete(userId);
  return beat.expiresAt > Date.now();
}

/** Everybody else on the conversation (the caller is never listed), replying first. */
export function viewersFor(conversationId: string, callerId: string): Viewer[] {
  const now = Date.now();
  const people = [...(presence.get(conversationId) ?? new Map<string, Beat>()).entries()];
  return people
    .filter(([userId, beat]) => userId !== callerId && beat.expiresAt > now)
    .map(([userId, beat]) => ({ user_id: userId, name: beat.name, state: beat.state }))
    .toSorted((a, b) => Number(b.state === "replying") - Number(a.state === "replying"));
}

/** Forget every beat (tests). */
export function resetPresence(): void {
  presence.clear();
}

type Announce = { type: LiveEventType; idParam?: string };

const APPOINTMENT_ID: readonly Announce[] = [
  { type: "appointments.changed", idParam: "appointment_id" },
];

const CARE_PATIENT: readonly Announce[] = [
  { type: "handoff.changed", idParam: "patient_id" },
  { type: "care.changed", idParam: "patient_id" },
];

/** Which mutation announces which event, by route template (what the real backend does on commit). */
const ANNOUNCE: Record<string, readonly Announce[]> = {
  "PATCH /api/v1/conversations/{conversation_id}": [
    { type: "inbox.changed", idParam: "conversation_id" },
  ],
  "POST /api/v1/conversations/{conversation_id}/messages": [
    { type: "inbox.changed", idParam: "conversation_id" },
  ],
  "POST /api/v1/conversations/{conversation_id}/read": [
    { type: "inbox.changed", idParam: "conversation_id" },
  ],
  "POST /api/v1/appointments": [{ type: "appointments.changed" }],
  "PATCH /api/v1/appointments/{appointment_id}": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/confirm": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/check-in": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/start": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/complete": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/cancel": APPOINTMENT_ID,
  "POST /api/v1/appointments/{appointment_id}/miss": APPOINTMENT_ID,
  "POST /api/v1/crm/tasks/{task_id}/resolve": [{ type: "tasks.changed", idParam: "task_id" }],
  "POST /api/v1/crm/activities": [{ type: "tasks.changed" }],
  "POST /api/v1/review-items/{item_id}/approve": [
    { type: "review.changed", idParam: "item_id" },
    { type: "inbox.changed" },
  ],
  "POST /api/v1/review-items/{item_id}/reject": [{ type: "review.changed", idParam: "item_id" }],
  "POST /api/v1/review-items/{item_id}/escalate": [{ type: "review.changed", idParam: "item_id" }],
  "POST /api/v1/care/handoffs/{patient_id}/accept": CARE_PATIENT,
  "POST /api/v1/care/handoffs/{patient_id}/decline": CARE_PATIENT,
  "POST /api/v1/care/patients/{patient_id}/release": CARE_PATIENT,
  "POST /api/v1/care/patients/{patient_id}/tell-agent": [
    { type: "care.changed", idParam: "patient_id" },
  ],
};

/** Called by the server after a successful request. */
export function announceChange(
  method: string,
  template: string,
  params: Record<string, string>,
): void {
  const entries = ANNOUNCE[`${method} ${template}`] ?? [];
  entries.forEach((entry) =>
    emitLive(entry.type, entry.idParam ? (params[entry.idParam] ?? null) : null),
  );
}
