// Calls of the schedule screen. One place for the six transitions so the page, the card and the sheet send
// the same body: the version the person looked at (a stale one is a 409 "version_conflict", never a silent
// overwrite) and, for a cancellation, the reason.
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import type { ScheduleAction } from "@/lib/ops/schedule-view";

type Appointment = Schemas["AppointmentOut"];

export type TransitionTarget = { id: string; version: number };

/** Move one appointment one step; resolves with the appointment as the BE now holds it. */
export function runTransition(
  action: ScheduleAction,
  target: TransitionTarget,
  reason: string | null = null,
): Promise<Appointment> {
  const request = {
    params: { path: { appointment_id: target.id } },
    body: { version: target.version, reason },
  };
  const calls: Record<ScheduleAction, () => Promise<Appointment>> = {
    confirm: () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/confirm", request)),
    "check-in": () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/check-in", request)),
    start: () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/start", request)),
    complete: () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/complete", request)),
    miss: () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/miss", request)),
    cancel: () => unwrap(http.POST("/api/v1/appointments/{appointment_id}/cancel", request)),
  };
  return calls[action]();
}

/** The first free start of a day for a patient (and a doctor), or null when the day has none. */
export async function fetchFreeSlot(query: {
  patientId: string;
  doctorId: string | null;
  day: string;
  durationMin: number;
}): Promise<string | null> {
  const answer = await unwrap(
    http.GET("/api/v1/appointments/free-slot", {
      params: {
        query: {
          patient_id: query.patientId,
          doctor_id: query.doctorId,
          day: query.day,
          duration_min: query.durationMin,
        },
      },
    }),
  );
  return answer.starts_at ?? null;
}
