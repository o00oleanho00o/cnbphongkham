// Mock of the "several people at once" backend: the event bus behind `GET /api/v1/events` (SSE) and a simulator
// that sends an event every now and then while somebody listens, so the screens can be seen reacting without a
// second person.
//
// Events say WHAT changed (type + object id), never the content.
import { EventEmitter } from "node:events";

export type LiveEventType = "tasks.changed" | "appointments.changed";
export type LiveMessage = { type: LiveEventType; id: string | null };

const SIMULATE_ROTATION: readonly LiveEventType[] = ["tasks.changed", "appointments.changed"];

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
    const type = SIMULATE_ROTATION[simulated % SIMULATE_ROTATION.length] ?? "tasks.changed";
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

type Announce = { type: LiveEventType; idParam?: string };

const APPOINTMENT_ID: readonly Announce[] = [
  { type: "appointments.changed", idParam: "appointment_id" },
];

/** Which mutation announces which event, by route template (what the real backend does on commit). */
const ANNOUNCE: Record<string, readonly Announce[]> = {
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
