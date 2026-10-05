"use client";

// Dòng thời gian agent theo khách: đã gửi gì, nháp chờ gì, vì sao chuyển người, nhắc đang tạm dừng.
import { TimelineView } from "@/components/care/timeline-view";
import { usePatientCare } from "@/components/care/patient-care-context";
import { useNow } from "@/lib/care/sla";

export default function PatientTimelinePage() {
  const { timeline } = usePatientCare();
  const now = useNow();
  if (!timeline.data) return null;
  return <TimelineView data={timeline.data} now={now} />;
}
