"use client";

// Frame of the three care pages of one patient: name and state on top, the pages as tabs, the care state loaded
// once for all of them (`PatientCareProvider`). A role without `care.read` sees a plain "no access" note; the
// backend refuses the calls anyway.
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconBot } from "@/components/admin/shared/dashboard-icons";
import { PatientCareProvider } from "@/components/care/patient-care-context";
import {
  ControlBadge,
  LevelBadge,
  NoAccess,
  SubNav,
  patientCareItems,
} from "@/components/care/care-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { useSession } from "@/lib/session/session-context";

export default function PatientCareLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const { can } = useSession();
  if (!can("care.read")) return <NoAccess what="xem agent chăm sóc của bệnh nhân" />;
  return (
    <PatientCareProvider patientId={params.id}>
      {({ patientId, timeline, liveMode }) => (
        <div className="mx-auto max-w-4xl">
          <PageHeader
            icon={IconBot}
            title={timeline.data?.patient_name ?? "Agent chăm sóc"}
            subtitle="Agent làm gì, đang giữ gì, đang chờ ai"
            aside={
              <div className="flex flex-wrap items-center gap-2">
                {timeline.data && <ControlBadge state={timeline.data.control.state} />}
                {timeline.data && <LevelBadge level={timeline.data.autonomy.effective_level} />}
                <Link
                  href={`/patients/${patientId}`}
                  className="inline-flex min-h-11 items-center text-[13px] font-medium text-brand-500 hover:text-brand-600"
                >
                  Hồ sơ bệnh nhân
                </Link>
              </div>
            }
          />
          <LiveStatus mode={liveMode} />
          <SubNav label="Agent chăm sóc của bệnh nhân" items={patientCareItems(patientId)} />
          {timeline.error && <RetryNotice message={timeline.error} onRetry={timeline.reload} />}
          {timeline.loading && !timeline.data && <ListSkeleton rows={3} />}
          {timeline.data && children}
        </div>
      )}
    </PatientCareProvider>
  );
}
