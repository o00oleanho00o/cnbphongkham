"use client";

// Nói với agent của khách: lời dặn tự do, lưu vào care_memory nguồn `staff`.
import { TellAgentForm } from "@/components/care/tell-agent-form";
import { usePatientCare } from "@/components/care/patient-care-context";

export default function PatientTellAgentPage() {
  const { patientId, timeline } = usePatientCare();
  if (!timeline.data) return null;
  return <TellAgentForm patientId={patientId} timeline={timeline.data} onDone={timeline.refresh} />;
}
