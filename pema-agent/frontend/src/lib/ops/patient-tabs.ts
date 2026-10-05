// The six tabs of Patient 360 (the sixth, Dịch vụ & tài chính, is step U9) and which role sees which (package U, step U3). A hidden tab is a convenience; the
// BE refuses the request behind it anyway. Labels are the ones of the old Clinic Web; `shortLabel` is for the
// segmented control of a phone.
import type { TabItem } from "@/ui/tabs";
import type { Permission } from "@/lib/session/session-context";

export type PatientTabKey = "overview" | "consult" | "plan" | "session" | "photos" | "finance";

export type PatientTab = TabItem & { id: PatientTabKey; needs: Permission };

export const PATIENT_TABS: readonly PatientTab[] = [
  { id: "overview", label: "Tổng quan", shortLabel: "Tổng quan", needs: "patient.read_360" },
  { id: "consult", label: "Tư vấn", shortLabel: "Tư vấn", needs: "session.read" },
  { id: "plan", label: "Kế hoạch", shortLabel: "Kế hoạch", needs: "patient.read_360" },
  { id: "session", label: "Buổi điều trị", shortLabel: "Buổi", needs: "session.read" },
  { id: "photos", label: "Ảnh trước / sau", shortLabel: "Ảnh", needs: "media.read" },
  {
    id: "finance",
    label: "Dịch vụ & tài chính",
    shortLabel: "Tài chính",
    needs: "patient.read_360",
  },
];

/** The tabs the caller may open, in order. `can` is `useSession().can`. */
export function visiblePatientTabs(can: (permission: Permission) => boolean): PatientTab[] {
  return PATIENT_TABS.filter((tab) => can(tab.needs));
}
