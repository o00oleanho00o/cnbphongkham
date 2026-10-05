// Fictional data of the Patient 360 dialogs (package U, step U9): warnings, history and diagnosis, notes on the
// patient app timeline and approved briefs. Everything is synthetic; the real rules live in the BE.
import { patientRef } from "./clinic";
import { plans } from "./patient-care";

import { isoFromNow, type Schemas } from "../core";

type S = Schemas;

export type StoredClinicalNote = S["ClinicalNoteOut"] & { patient_id: string };
export type StoredAppUpdate = S["AppUpdateOut"] & { patient_id: string };
export type StoredBrief = S["BriefApprovedOut"] & { patient_id: string };

/** `Thông tin cần nhớ` of each patient, by patient id. */
export const alertsByPatient: Record<string, string[]> = {
  [patientRef(1).id]: ["Da nhạy cảm (mẫu)", "Theo dõi đỏ da sau điều trị (mẫu)"],
};

export const clinicalNotes: StoredClinicalNote[] = [
  {
    patient_id: patientRef(1).id,
    history: "Nám mảng hai bên má, dùng kem chống nắng không đều (mẫu).",
    diagnosis: "Tăng sắc tố sau viêm, đáp ứng tốt với phác đồ hiện tại (mẫu).",
    reviewed_by_name: "BS. Lê Minh Tâm",
    reviewed_at: isoFromNow(-6 * 86_400_000),
  },
];

export const appUpdates: StoredAppUpdate[] = [];
export const briefs: StoredBrief[] = [];

// The first synthetic course of patient 1 was added with a fixed price (U9).
const firstPlan = plans.find((p) => p.patient_id === patientRef(1).id);
if (firstPlan) {
  firstPlan.unit_price_vnd = 2_500_000;
  firstPlan.discount_vnd = 500_000;
  firstPlan.agreed_price_vnd = firstPlan.total_sessions * 2_500_000 - 500_000;
  firstPlan.service_terms_version = 1;
}
