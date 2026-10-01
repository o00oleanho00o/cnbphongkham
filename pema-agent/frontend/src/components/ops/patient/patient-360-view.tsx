"use client";

// Patient 360, read only. It connects context (appointments, plan, CRM, conversations, consents) but the
// original record stays the source of truth (AGENT.md). Internal CSKH notes are marked internal and are
// never shown to the patient. On a phone the sections are tabs (one child screen of work at a time); from
// `lg` they sit in a two-column grid.
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import { PriorityBadge } from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { ageYears, dueLabel, formatDate, formatDateTime } from "@/lib/ops/format";
import {
  APPOINTMENT_STATUS_LABEL,
  CHANNEL_LABEL,
  CONSENT_KIND_LABEL,
  CONVERSATION_STATUS_LABEL,
  EXPECTED_SOURCE_LABEL,
  GENDER_LABEL,
  LIFECYCLE_LABEL,
  OUTCOME_LABEL,
  RULE_LABEL,
} from "@/lib/ops/labels";

type P360 = Schemas["Patient360"];

type SectionKey = "overview" | "care" | "treatment" | "talk" | "consent";

const SECTION_LABEL: Record<SectionKey, string> = {
  overview: "Tổng quan",
  care: "Chăm sóc",
  treatment: "Lịch và điều trị",
  talk: "Hội thoại",
  consent: "Đồng ý",
};
const SECTIONS = Object.keys(SECTION_LABEL) as SectionKey[];

function Card({
  title,
  section,
  active,
  children,
  aside,
}: {
  title: string;
  section: SectionKey;
  active: SectionKey;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className={`gc-card p-4 sm:p-5 ${active === section ? "block" : "hidden"} lg:block`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-ink-soft">{label}</dt>
      <dd className="text-[14px] font-medium text-ink">{value}</dd>
    </div>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-ink-soft">{children}</p>;
}

export function Patient360View({ data }: { data: P360 }) {
  const [active, setActive] = useState<SectionKey>("overview");
  const { patient, profile } = data;
  const age = ageYears(patient.birth_date);
  const stage = LIFECYCLE_LABEL[profile.lifecycle_stage] ?? profile.lifecycle_stage;
  const upcoming = (data.appointments ?? [])
    .filter((a) => a.status === "booked" || a.status === "confirmed" || a.status === "arrived")
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at));
  const past = (data.appointments ?? [])
    .filter((a) => !upcoming.includes(a))
    .toSorted((a, b) => b.starts_at.localeCompare(a.starts_at));

  return (
    <div className="space-y-4">
      <header className="gc-card flex flex-wrap items-center gap-4 p-4 sm:p-5">
        <InitialAvatar name={patient.full_name} />
        <div className="min-w-0 flex-1">
          <h1 className="text-[20px] font-semibold text-ink">{patient.full_name}</h1>
          <p className="text-[13px] text-ink-soft">
            {patient.code} · {GENDER_LABEL[patient.gender ?? "unknown"]}
            {age !== null ? ` · ${age} tuổi` : ""}
            {patient.doctor_name ? ` · ${patient.doctor_name}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
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
        </div>
      </header>

      <div
        role="tablist"
        aria-label="Phần hồ sơ"
        className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:hidden"
      >
        {SECTIONS.map((key) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={active === key}
            onClick={() => setActive(key)}
            className={`min-h-11 rounded-full border px-4 text-[13px] font-medium whitespace-nowrap ${
              active === key
                ? "border-brand-500 bg-brand-500 text-white"
                : "border-line bg-surface text-ink-soft"
            }`}
          >
            {SECTION_LABEL[key]}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Thông tin" section="overview" active={active}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="Ngày sinh" value={formatDate(patient.birth_date)} />
            <Fact label="Nguồn" value={patient.source ?? "-"} />
            <Fact label="Liên hệ đầu tiên" value={formatDate(patient.first_contact_at)} />
            <Fact label="Phụ trách CSKH" value={patient.cs_owner_name ?? "-"} />
            <Fact label="Điện thoại" value={patient.phone ?? "Chưa lưu"} />
            <Fact label="Bác sĩ phụ trách" value={patient.doctor_name ?? "-"} />
          </dl>
        </Card>

        <Card title="Chăm sóc sau điều trị" section="care" active={active}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="Lần khám gần nhất" value={formatDate(profile.last_visit_at)} />
            <Fact
              label="Dự kiến tái khám"
              value={
                profile.expected_next_visit_at
                  ? `${formatDate(profile.expected_next_visit_at)}${
                      profile.expected_visit_source
                        ? ` · ${EXPECTED_SOURCE_LABEL[profile.expected_visit_source] ?? profile.expected_visit_source}`
                        : ""
                    }`
                  : "Chưa có"
              }
            />
            <Fact label="Quá hạn" value={`${profile.overdue_days ?? 0} ngày`} />
            <Fact label="Còn lại" value={`${profile.remaining_sessions ?? 0} buổi`} />
          </dl>
        </Card>

        <Card
          title={`Việc chăm sóc đang mở (${data.open_tasks?.length ?? 0})`}
          section="care"
          active={active}
        >
          {(data.open_tasks ?? []).length === 0 ? (
            <Muted>Không có việc đang mở.</Muted>
          ) : (
            <ul className="space-y-2">
              {(data.open_tasks ?? []).map((t) => (
                <li key={t.id} className="rounded-lg border border-line px-3 py-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold text-ink">
                      {RULE_LABEL[t.rule_key]}
                    </span>
                    <PriorityBadge priority={t.priority} />
                  </div>
                  <p className="mt-0.5 text-[13px] text-ink-soft">{t.reason}</p>
                  <p className="mt-0.5 text-[12px] text-ink-soft">{dueLabel(t.due_at)}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[13px]">
            <Link href="/today" className="text-brand-500 underline">
              Mở Việc hôm nay
            </Link>
          </p>
        </Card>

        <Card title="Lịch hẹn" section="treatment" active={active}>
          {upcoming.length === 0 && past.length === 0 && <Muted>Chưa có lịch hẹn.</Muted>}
          <ul className="space-y-2">
            {[...upcoming, ...past.slice(0, 4)].map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5"
              >
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold text-ink">
                    {formatDateTime(a.starts_at)}
                  </div>
                  <div className="truncate text-[12px] text-ink-soft">{a.note ?? "Lịch hẹn"}</div>
                </div>
                <Badge tone={upcoming.includes(a) ? "blue" : "gray"} dot={false}>
                  {APPOINTMENT_STATUS_LABEL[a.status]}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Liệu trình" section="treatment" active={active}>
          {(data.plans ?? []).length === 0 && (data.episodes ?? []).length === 0 && (
            <Muted>Chưa có liệu trình.</Muted>
          )}
          {(data.episodes ?? []).map((e) => (
            <p key={e.id} className="mb-2 text-[13px] text-ink">
              <strong>{e.title}</strong>{" "}
              <span className="text-ink-soft">· từ {formatDate(e.started_on)}</span>
            </p>
          ))}
          <ul className="space-y-3">
            {(data.plans ?? []).map((plan) => {
              const percent = Math.round(
                (plan.completed_sessions / Math.max(1, plan.total_sessions)) * 100,
              );
              return (
                <li key={plan.id}>
                  <div className="flex items-baseline justify-between gap-2 text-[13px]">
                    <span className="font-medium text-ink">{plan.title}</span>
                    <span className="text-ink-soft">
                      {plan.completed_sessions}/{plan.total_sessions} buổi
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Tiến độ ${plan.title}`}
                    className="mt-1.5 h-2 overflow-hidden rounded-full bg-tile"
                  >
                    <div
                      className="h-full rounded-full bg-brand-500"
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
          {(data.recent_sessions ?? []).length > 0 && (
            <ul className="mt-4 space-y-1.5 border-t border-line pt-3">
              {(data.recent_sessions ?? []).map((s) => (
                <li key={s.id} className="text-[13px] text-ink-soft">
                  {formatDate(s.performed_at)} · {s.title}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Ghi nhận chăm sóc (nội bộ)" section="care" active={active}>
          <p className="mb-2 text-[12px] text-ink-soft">
            Nội dung liên hệ nội bộ không hiển thị cho người bệnh.
          </p>
          {(data.recent_activities ?? []).length === 0 && <Muted>Chưa có ghi nhận.</Muted>}
          <ul className="space-y-2">
            {(data.recent_activities ?? []).map((a) => (
              <li key={a.id} className="rounded-lg border border-line px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-x-2 text-[12px] text-ink-soft">
                  <span>{formatDateTime(a.occurred_at)}</span>
                  <span>· {CHANNEL_LABEL[a.channel]}</span>
                  {a.outcome && <span>· {OUTCOME_LABEL[a.outcome]}</span>}
                  {a.actor_name && <span>· {a.actor_name}</span>}
                </div>
                <p className="mt-0.5 text-[13px] text-ink">{a.note}</p>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Hội thoại" section="talk" active={active}>
          {(data.conversations ?? []).length === 0 && <Muted>Chưa có hội thoại.</Muted>}
          <ul className="space-y-2">
            {(data.conversations ?? []).map((c) => (
              <li key={c.id}>
                <Link
                  href={`/inbox?c=${c.id}`}
                  className="block rounded-lg border border-line px-3 py-2.5 hover:bg-tile/50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] text-ink-soft">
                      {formatDateTime(c.last_message_at)}
                    </span>
                    <Badge tone="gray" dot={false}>
                      {CONVERSATION_STATUS_LABEL[c.status]}
                    </Badge>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[13px] text-ink">
                    {c.last_message_preview}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Đồng ý của khách" section="consent" active={active}>
          {(data.consents ?? []).length === 0 && <Muted>Chưa ghi nhận đồng ý nào.</Muted>}
          <ul className="space-y-2">
            {(data.consents ?? []).map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="text-ink">{CONSENT_KIND_LABEL[c.kind]}</span>
                <Badge tone={c.granted ? "green" : "gray"} dot={false}>
                  {c.granted ? "Đã đồng ý" : "Chưa đồng ý"}
                </Badge>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[12px] text-ink-soft">
            Đồng ý hình ảnh và tin quảng bá được kiểm tra trước khi hệ thống chuẩn bị tin cho khách.
          </p>
        </Card>

        <Card title="Dòng thời gian" section="care" active={active}>
          {(data.timeline ?? []).length === 0 && <Muted>Chưa có sự kiện.</Muted>}
          <ol className="ml-1.5 space-y-3 border-l border-line pl-4">
            {(data.timeline ?? []).slice(0, 8).map((ev) => (
              <li key={ev.id} className="relative">
                <span className="absolute top-1.5 -left-[21px] h-2 w-2 rounded-full bg-brand-400" />
                <div className="text-[12px] text-ink-soft">{formatDateTime(ev.at)}</div>
                <div className="text-[13px] font-medium text-ink">{ev.title}</div>
                {ev.detail && <div className="text-[12px] text-ink-soft">{ev.detail}</div>}
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <p className="text-[12px] text-ink-soft">
        Patient 360 chỉ tổng hợp ngữ cảnh để xem nhanh. Hồ sơ, lịch và liệu trình gốc vẫn là nguồn
        sự thật.
      </p>
    </div>
  );
}
