// Shared set-up of the Patient 360 tab tests: a signed-in session with chosen permissions, the toast host, and the
// shape of an `openapi-fetch` answer. The typed client itself is replaced in each test file (`vi.mock`): it is the
// network, the one dependency these tests do not own.
import type { ReactNode } from "react";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

export const PATIENT_ID = "00000000-0000-4000-8002-000000000001";

export function ok<T>(data: T): { data: T; response: Response } {
  return { data, response: new Response(null, { status: 200 }) };
}

export function asRole(permissions: Permission[], children: ReactNode) {
  return (
    <SessionProvider
      user={{
        id: "00000000-0000-4000-8001-000000000003",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "BS. Lê Minh Tâm",
        role: "doctor",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>{children}</ToastProvider>
    </SessionProvider>
  );
}

export function plan(
  overrides: Partial<Schemas["TreatmentPlanOut"]> = {},
): Schemas["TreatmentPlanOut"] {
  return {
    id: "plan-1",
    episode_id: null,
    service_code: "laser-co2",
    title: "Laser CO2 phục hồi da",
    total_sessions: 4,
    completed_sessions: 2,
    status: "active",
    goal: null,
    doctor_id: null,
    version: 3,
    ...overrides,
  };
}

export function photo(overrides: Partial<Schemas["MediaOut"]> = {}): Schemas["MediaOut"] {
  return {
    id: "media-1",
    patient_id: PATIENT_ID,
    session_id: null,
    stage: "before",
    region: "Mặt",
    view: "Chính diện",
    mime: "image/png",
    size_bytes: 100,
    status: "confirmed",
    consent_id: "consent-1",
    consent_active: true,
    created_at: "2026-09-20T09:00:00+07:00",
    content_path: "/api/v1/media/media-1/content",
    version: 3,
    ...overrides,
  };
}
