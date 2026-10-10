"use client";

// Patient 360 with five tabs: Tổng quan, Tư vấn, Kế hoạch, Buổi điều trị, Ảnh (the old Clinic Web tabs). The tab
// is kept in `?tab=` so a link opens a tab and the browser's back button works; a tab is mounted the first time
// it is opened and then kept (hidden) so a half-written session form survives a look at the photos. Which tabs
// show depends on the permissions of the signed-in role; the BE still decides every request.
//   overview  patient.read_360 (everyone who opens the 360)
//   consult   session.read     (notes: write needs session.write)
//   plan      patient.read_360 (create and edit need session.write)
//   session   session.read     (the form needs session.write)
//   photos    media.read       (upload needs media.write)
//   finance   patient.read_360 (amounts and buttons follow finance.* and order.*; U9)
// The header carries "AI brief" (session.write: a template, a doctor approves it) and "Nhắn tin"
// (conversation.reply); the cards of Tổng quan open "Thông tin cần nhớ", "Chăm sóc tại nhà" and
// "Ngày dự kiến quay lại".
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { InitialAvatar, Badge } from "@/components/admin/shared/ui-bits";
import { ConsultTab } from "@/components/ops/patient/consult-tab";
import { FinanceTab } from "@/components/ops/patient/finance-tab";
import {
  AftercareDialog,
  BriefDialog,
  ExpectedReturnDialog,
  FactsDialog,
  MessageDialog,
} from "@/components/ops/patient/patient-dialogs";
import { OverviewTab } from "@/components/ops/patient/overview-tab";
import { PhotosTab } from "@/components/ops/patient/photos-tab";
import { PlanTab } from "@/components/ops/patient/plan-tab";
import { SessionTab } from "@/components/ops/patient/session-tab";
import type { Schemas } from "@/lib/api";
import { ageYears } from "@/lib/ops/format";
import { GENDER_LABEL, LIFECYCLE_LABEL } from "@/lib/ops/labels";
import { visiblePatientTabs, type PatientTabKey } from "@/lib/ops/patient-tabs";
import { useSession } from "@/lib/session/session-context";
import { Button } from "@/ui/button";
import { Tabs } from "@/ui/tabs";

type P360 = Schemas["Patient360"];
type DialogKey = "brief" | "message" | "facts" | "aftercare" | "expected";

const ID_PREFIX = "p360";

export function Patient360View({ data, onChanged }: { data: P360; onChanged: () => void }) {
  const { can } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const { patient, profile } = data;

  const tabs = visiblePatientTabs(can);
  const requested = search.get("tab");
  const active: PatientTabKey = tabs.find((t) => t.id === requested)?.id ?? "overview";
  const [dialog, setDialog] = useState<DialogKey | null>(null);
  const [opened, setOpened] = useState<ReadonlySet<PatientTabKey>>(new Set([active]));
  const mounted = new Set([...opened, active]);

  function select(id: string) {
    const tab = tabs.find((t) => t.id === id);
    if (tab === undefined) return;
    setOpened((current) => new Set([...current, tab.id]));
    const next = new URLSearchParams(search.toString());
    if (tab.id === "overview") next.delete("tab");
    else next.set("tab", tab.id);
    const query = next.toString();
    router.replace(query === "" ? pathname : `${pathname}?${query}`, { scroll: false });
  }

  const age = ageYears(patient.birth_date);
  const stage = LIFECYCLE_LABEL[profile.lifecycle_stage] ?? profile.lifecycle_stage;
  const consent = (data.consents ?? []).find((c) => c.kind === "media");
  const consentGranted = consent?.granted === true;
  const plans = data.plans ?? [];
  const nextBooked = (data.appointments ?? [])
    .filter((a) => ["booked", "confirmed", "arrived"].includes(a.status))
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at))
    .at(0);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center gap-4 rounded-hero border border-brand-100 bg-brand-50 p-4 sm:p-5">
        <InitialAvatar name={patient.full_name} />
        <div className="min-w-0 flex-1 basis-48">
          <h1 className="text-title font-bold text-heading">{patient.full_name}</h1>
          <p className="text-small text-ink-soft">
            {patient.code} · {GENDER_LABEL[patient.gender ?? "unknown"]}
            {age !== null ? ` · ${age} tuổi` : ""}
            {patient.doctor_name ? ` · ${patient.doctor_name}` : ""}
          </p>
          {(data.alerts ?? []).length > 0 && (
            <ul aria-label="Thông tin cần nhớ" className="mt-1.5 flex flex-wrap gap-1.5">
              {(data.alerts ?? []).map((alert) => (
                <li key={alert}>
                  <Badge tone="amber" dot={false}>
                    ⚠ {alert}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex w-full flex-wrap items-center gap-1.5 sm:w-auto">
          <Badge tone="blue" dot={false}>
            {stage}
          </Badge>
          {profile.marketing_opt_out && (
            <Badge tone="amber" dot={false}>
              Từ chối tin quảng bá
            </Badge>
          )}
          {profile.risk_level === "high" && (
            <Badge tone="red" dot={false}>
              Cần theo dõi
            </Badge>
          )}
          {can("session.write") && (
            <Button variant="secondary" onClick={() => setDialog("brief")}>
              ✦ AI brief
            </Button>
          )}
          {can("conversation.reply") && (
            <Button variant="secondary" onClick={() => setDialog("message")}>
              Nhắn tin
            </Button>
          )}
          {can("session.write") && (
            <Button onClick={() => select("session")}>＋ Ghi buổi điều trị</Button>
          )}
        </div>
      </header>

      <Tabs
        label="Phần hồ sơ"
        idPrefix={ID_PREFIX}
        items={tabs}
        value={active}
        onChange={select}
        segmentedOnPhone
      />

      {tabs.map((tab) => {
        if (!mounted.has(tab.id)) return null;
        return (
          <div
            key={tab.id}
            role="tabpanel"
            id={`${ID_PREFIX}-panel-${tab.id}`}
            aria-labelledby={`${ID_PREFIX}-tab-${tab.id}`}
            hidden={tab.id !== active}
          >
            {tab.id === "overview" && (
              <OverviewTab
                data={data}
                onEditFacts={can("session.write") ? () => setDialog("facts") : undefined}
                onAftercare={can("session.write") ? () => setDialog("aftercare") : undefined}
                onExpected={can("crm.activity.write") ? () => setDialog("expected") : undefined}
              />
            )}
            {tab.id === "consult" && (
              <ConsultTab
                patientId={patient.id}
                canWrite={can("session.write")}
                onChanged={onChanged}
              />
            )}
            {tab.id === "plan" && (
              <PlanTab
                patientId={patient.id}
                plans={plans}
                doctorName={patient.doctor_name}
                nextVisit={nextBooked?.starts_at}
                canWrite={can("session.write")}
                onChanged={onChanged}
              />
            )}
            {tab.id === "session" && (
              <SessionTab
                patientId={patient.id}
                plans={plans}
                alerts={[]}
                consentGranted={consentGranted}
                canWrite={can("session.write")}
                canRecordConsent={can("consent.write")}
                canUpload={can("media.write")}
                canReadMedia={can("media.read")}
                onSaved={onChanged}
              />
            )}
            {tab.id === "finance" && (
              <FinanceTab patient={patient} plans={plans} onChanged={onChanged} />
            )}
            {tab.id === "photos" && (
              <PhotosTab
                patientId={patient.id}
                consentGranted={consentGranted}
                canUpload={can("media.write")}
                canRecordConsent={can("consent.write")}
                onChanged={onChanged}
              />
            )}
          </div>
        );
      })}

      {dialog === "brief" && <BriefDialog data={data} onClose={() => setDialog(null)} />}
      {dialog === "message" && (
        <MessageDialog data={data} onClose={() => setDialog(null)} onSent={onChanged} />
      )}
      {dialog === "aftercare" && (
        <AftercareDialog
          patientId={patient.id}
          onClose={() => setDialog(null)}
          onSent={onChanged}
        />
      )}
      {dialog === "facts" && (
        <FactsDialog
          data={data}
          canRecordConsent={can("consent.write")}
          onClose={() => setDialog(null)}
          onSaved={onChanged}
        />
      )}
      {dialog === "expected" && (
        <ExpectedReturnDialog data={data} onClose={() => setDialog(null)} onSaved={onChanged} />
      )}
    </div>
  );
}
