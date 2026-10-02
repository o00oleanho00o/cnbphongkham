// Calls of the care supervision screens (`/api/v1/care/**`, backend `pema/api/routers/care.py`) through the typed
// client. One function per operation, so a screen never builds a URL or a body by hand and the tests of a
// screen can fake this one module. Every answer is the backend's decision; nothing is computed here.
import { http, unwrap } from "@/lib/api/client";
import type {
  CareMatrixIn,
  CareTimingIn,
  OnCallContactIn,
  ReleaseIn,
  StaffCareProfileIn,
} from "@/lib/care/care-types";
import type { Schemas } from "@/lib/api";

export type HandoffScope = "mine" | "all";

export const careApi = {
  handoffs: (scope: HandoffScope, signal?: AbortSignal) =>
    unwrap(http.GET("/api/v1/care/handoffs", { params: { query: { scope } }, signal })),

  accept: (patientId: string) =>
    unwrap(
      http.POST("/api/v1/care/handoffs/{patient_id}/accept", {
        params: { path: { patient_id: patientId } },
      }),
    ),

  decline: (patientId: string, reason: string, suggestUserId: string | null) =>
    unwrap(
      http.POST("/api/v1/care/handoffs/{patient_id}/decline", {
        params: { path: { patient_id: patientId } },
        body: { reason, suggest_user_id: suggestUserId },
      }),
    ),

  timeline: (patientId: string, signal?: AbortSignal) =>
    unwrap(
      http.GET("/api/v1/care/patients/{patient_id}/timeline", {
        params: { path: { patient_id: patientId } },
        signal,
      }),
    ),

  previewRelease: (patientId: string, body: ReleaseIn, signal?: AbortSignal) =>
    unwrap(
      http.POST("/api/v1/care/patients/{patient_id}/release/preview", {
        params: { path: { patient_id: patientId } },
        body,
        signal,
      }),
    ),

  release: (patientId: string, body: ReleaseIn) =>
    unwrap(
      http.POST("/api/v1/care/patients/{patient_id}/release", {
        params: { path: { patient_id: patientId } },
        body,
      }),
    ),

  tellAgent: (patientId: string, instruction: string) =>
    unwrap(
      http.POST("/api/v1/care/patients/{patient_id}/tell-agent", {
        params: { path: { patient_id: patientId } },
        body: { instruction },
      }),
    ),

  staff: (signal?: AbortSignal) => unwrap(http.GET("/api/v1/care/admin/staff", { signal })),

  saveStaff: (userId: string, body: StaffCareProfileIn) =>
    unwrap(
      http.PUT("/api/v1/care/admin/staff/{user_id}", {
        params: { path: { user_id: userId } },
        body,
      }),
    ),

  onCall: (signal?: AbortSignal) => unwrap(http.GET("/api/v1/care/admin/on-call", { signal })),

  createOnCall: (body: OnCallContactIn) =>
    unwrap(http.POST("/api/v1/care/admin/on-call", { body })),

  saveOnCall: (contactId: string, body: OnCallContactIn) =>
    unwrap(
      http.PUT("/api/v1/care/admin/on-call/{contact_id}", {
        params: { path: { contact_id: contactId } },
        body,
      }),
    ),

  matrix: (signal?: AbortSignal) => unwrap(http.GET("/api/v1/care/admin/matrix", { signal })),

  saveMatrix: (body: CareMatrixIn) => unwrap(http.PUT("/api/v1/care/admin/matrix", { body })),

  approveMatrix: (approved: boolean, version: number) =>
    unwrap(http.POST("/api/v1/care/admin/matrix/approval", { body: { approved, version } })),

  timing: (signal?: AbortSignal) => unwrap(http.GET("/api/v1/care/admin/timing", { signal })),

  saveTiming: (body: CareTimingIn) => unwrap(http.PUT("/api/v1/care/admin/timing", { body })),

  alerts: (signal?: AbortSignal) => unwrap(http.GET("/api/v1/care/admin/alerts", { signal })),
};

export type HandoffList = Schemas["HandoffListOut"];
