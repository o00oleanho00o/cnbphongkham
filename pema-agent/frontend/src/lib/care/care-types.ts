// Types of the care-agent supervision screens, all from the generated client (`Schemas[...]`, backend
// `pema_contracts/care.py`). Nothing is declared by hand: a change of the contract fails `tsc` here.
import type { Schemas } from "@/lib/api";

export type CareControlState = Schemas["CareControlState"];
export type CareDepth = Schemas["CareDepth"];
export type CareLevel = Schemas["CareLevel"];
export type CareUrgency = Schemas["CareUrgency"];
export type HandoffWaiting = Schemas["HandoffWaitingOut"];
export type HandoffResult = Schemas["HandoffResultOut"];
export type PatientCareTimeline = Schemas["PatientCareTimelineOut"];
export type TimelineEntry = Schemas["TimelineEntryOut"];
export type ReleaseIn = Schemas["ReleaseIn"];
export type ReleasePreview = Schemas["ReleasePreviewOut"];
export type StaffCareProfile = Schemas["StaffCareProfileOut"];
export type StaffCareProfileIn = Schemas["StaffCareProfileIn"];
export type Shift = Schemas["ShiftOut"];
export type ShiftInterval = Schemas["ShiftIntervalOut"];
export type OnCallContact = Schemas["OnCallContactOut"];
export type OnCallContactIn = Schemas["OnCallContactIn"];
export type CareMatrix = Schemas["CareMatrixOut"];
export type CareMatrixIn = Schemas["CareMatrixIn"];
export type DepthSignal = Schemas["DepthSignal"];
export type CareTiming = Schemas["CareTimingOut"];
export type CareTimingIn = Schemas["CareTimingIn"];
export type CareAlert = Schemas["CareAlertOut"];
export type CareAlertKind = Schemas["CareAlertKind"];

export const DEPTHS: readonly CareDepth[] = ["D1", "D2", "D3", "D4", "D5"];
export const LEVELS: readonly CareLevel[] = ["L0", "L1", "L2"];
export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Weekday = (typeof WEEKDAYS)[number];
