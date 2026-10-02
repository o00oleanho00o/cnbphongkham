"use client";

// The care state of ONE patient, loaded once for the three pages of `/care/patients/[id]/*` (timeline, release,
// tell-agent). A `care.changed` or `handoff.changed` event for this patient (or for "some": a doctor's stream
// carries no ids) reloads it quietly, so a colleague accepting or releasing the conversation shows here without a
// refresh and nothing the person is typing is touched.
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { careApi } from "@/lib/care/care-api";
import type { PatientCareTimeline } from "@/lib/care/care-types";
import type { LiveEvent, LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import type { LiveMode } from "@/lib/live/live-connection";
import { useLoad, type LoadState } from "@/lib/use-load";

const LIVE_TYPES: readonly LiveEventType[] = ["care.changed", "handoff.changed"];

type PatientCareValue = {
  patientId: string;
  timeline: LoadState<PatientCareTimeline>;
  liveMode: LiveMode;
};

const PatientCareContext = createContext<PatientCareValue | null>(null);

export function PatientCareProvider({
  patientId,
  children,
}: {
  patientId: string;
  children: (value: PatientCareValue) => ReactNode;
}) {
  const load = useCallback(
    (signal: AbortSignal) => careApi.timeline(patientId, signal),
    [patientId],
  );
  const timeline = useLoad(load);
  const { refresh } = timeline;
  const onEvent = useCallback(
    (event: LiveEvent) => {
      if (event.id === null || event.id === patientId) refresh();
    },
    [patientId, refresh],
  );
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent, onRefresh: refresh });
  const value = useMemo(() => ({ patientId, timeline, liveMode }), [patientId, timeline, liveMode]);
  return <PatientCareContext.Provider value={value}>{children(value)}</PatientCareContext.Provider>;
}

export function usePatientCare(): PatientCareValue {
  const value = useContext(PatientCareContext);
  if (!value) throw new Error("usePatientCare must be used inside PatientCareProvider");
  return value;
}
