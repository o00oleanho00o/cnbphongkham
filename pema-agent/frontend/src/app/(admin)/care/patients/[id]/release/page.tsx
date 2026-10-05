"use client";

// Trả lại cho agent: ghi chú bàn giao và (tùy chọn) hạ mức tự chủ có thời hạn.
import { ReleaseForm } from "@/components/care/release-form";
import { usePatientCare } from "@/components/care/patient-care-context";

export default function PatientReleasePage() {
  const { patientId, timeline } = usePatientCare();
  if (!timeline.data) return null;
  return <ReleaseForm patientId={patientId} timeline={timeline.data} onDone={timeline.refresh} />;
}
