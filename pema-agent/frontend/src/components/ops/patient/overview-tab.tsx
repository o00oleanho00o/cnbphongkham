"use client";

// Tổng quan tab: everything Patient 360 showed before the tabs (information, care after treatment, open tasks,
// appointments, plan progress, internal care notes, conversations, consents, timeline) plus the three-figure
// summary of the old Clinic Web. Read only: the original records stay the source of truth (AGENT.md). Internal
// CSKH notes are marked internal and never shown to the patient.
import Link from "next/link";

import { PriorityBadge } from "@/components/ops/ops-ui";
import { Fact, Muted } from "@/components/ops/patient/shared";
import { Badge } from "@/components/admin/shared/ui-bits";
import type { Schemas } from "@/lib/api";
import { dueLabel, formatDate, formatDateTime } from "@/lib/ops/format";
import {
  APPOINTMENT_STATUS_LABEL,
  CHANNEL_LABEL,
  CONSENT_KIND_LABEL,
  CONVERSATION_STATUS_LABEL,
  EXPECTED_SOURCE_LABEL,
  OUTCOME_LABEL,
  RULE_LABEL,
} from "@/lib/ops/labels";
import { Card } from "@/ui/card";
import { Tile } from "@/ui/tile";

type P360 = Schemas["Patient360"];

const BOOKED_STATUSES = ["booked", "confirmed", "arrived"];

/** Plan the summary speaks about: the live one with sessions left, else the first. */
function leadPlan(plans: P360["plans"]): Schemas["TreatmentPlanOut"] | undefined {
  const list = plans ?? [];
  const live = list.filter((p) => p.status === "planned" || p.status === "active");
  return live.at(0) ?? list.at(0);
}

export function OverviewTab({ data }: { data: P360 }) {
  const { patient, profile } = data;
  const upcoming = (data.appointments ?? [])
    .filter((a) => BOOKED_STATUSES.includes(a.status))
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at));
  const past = (data.appointments ?? [])
    .filter((a) => !upcoming.includes(a))
    .toSorted((a, b) => b.starts_at.localeCompare(a.starts_at));
  const plan = leadPlan(data.plans);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Tile
          label="Liệu trình hiện tại"
          value={<span className="text-section">{plan?.title ?? "Chưa có"}</span>}
        />
        <Tile
          label="Buổi đã hoàn tất"
          value={plan ? `${plan.completed_sessions} / ${plan.total_sessions}` : "-"}
          note="buổi"
        />
        <Tile
          label="Hẹn tiếp theo"
          value={
            <span className="text-section">
              {upcoming[0] ? formatDateTime(upcoming[0].starts_at) : "Chưa đặt lịch"}
            </span>
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Thông tin">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="Ngày sinh" value={formatDate(patient.birth_date)} />
            <Fact label="Nguồn" value={patient.source ?? "-"} />
            <Fact label="Liên hệ đầu tiên" value={formatDate(patient.first_contact_at)} />
            <Fact label="Phụ trách CSKH" value={patient.cs_owner_name ?? "-"} />
            <Fact label="Điện thoại" value={patient.phone ?? "Chưa lưu"} />
            <Fact label="Bác sĩ phụ trách" value={patient.doctor_name ?? "-"} />
          </dl>
        </Card>

        <Card title="Chăm sóc sau điều trị">
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

        <Card title={`Việc chăm sóc đang mở (${data.open_tasks?.length ?? 0})`}>
          {(data.open_tasks ?? []).length === 0 ? (
            <Muted>Không có việc đang mở.</Muted>
          ) : (
            <ul className="space-y-2">
              {(data.open_tasks ?? []).map((t) => (
                <li key={t.id} className="rounded-control border border-line px-3 py-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-small font-semibold text-ink">
                      {RULE_LABEL[t.rule_key]}
                    </span>
                    <PriorityBadge priority={t.priority} />
                  </div>
                  <p className="mt-0.5 text-small text-ink-soft">{t.reason}</p>
                  <p className="mt-0.5 text-label text-ink-soft">{dueLabel(t.due_at)}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-small">
            <Link href="/today" className="text-link underline">
              Mở Việc hôm nay
            </Link>
          </p>
        </Card>

        <Card title="Lịch hẹn">
          {upcoming.length === 0 && past.length === 0 && <Muted>Chưa có lịch hẹn.</Muted>}
          <ul className="space-y-2">
            {[...upcoming, ...past.slice(0, 4)].map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-control border border-line px-3 py-2.5"
              >
                <div className="min-w-0">
                  <div className="text-small font-semibold text-ink">
                    {formatDateTime(a.starts_at)}
                  </div>
                  <div className="truncate text-label text-ink-soft">{a.note ?? "Lịch hẹn"}</div>
                </div>
                <Badge tone={upcoming.includes(a) ? "blue" : "gray"} dot={false}>
                  {APPOINTMENT_STATUS_LABEL[a.status]}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Liệu trình">
          {(data.plans ?? []).length === 0 && (data.episodes ?? []).length === 0 && (
            <Muted>Chưa có liệu trình.</Muted>
          )}
          {(data.episodes ?? []).map((e) => (
            <p key={e.id} className="mb-2 text-small text-ink">
              <strong>{e.title}</strong>{" "}
              <span className="text-ink-soft">· từ {formatDate(e.started_on)}</span>
            </p>
          ))}
          <ul className="space-y-3">
            {(data.plans ?? []).map((p) => {
              const percent = Math.round(
                (p.completed_sessions / Math.max(1, p.total_sessions)) * 100,
              );
              return (
                <li key={p.id}>
                  <div className="flex items-baseline justify-between gap-2 text-small">
                    <span className="min-w-0 font-medium break-words text-ink">{p.title}</span>
                    <span className="text-ink-soft">
                      {p.completed_sessions}/{p.total_sessions} buổi
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Tiến độ ${p.title}`}
                    className="mt-1.5 h-2 overflow-hidden rounded-pill bg-tile"
                  >
                    <div
                      className="h-full rounded-pill bg-brand-500"
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
                <li key={s.id} className="text-small break-words text-ink-soft">
                  {formatDate(s.performed_at)} · {s.title}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Ghi nhận chăm sóc (nội bộ)">
          <p className="mb-2 text-label text-ink-soft">
            Nội dung liên hệ nội bộ không hiển thị cho người bệnh.
          </p>
          {(data.recent_activities ?? []).length === 0 && <Muted>Chưa có ghi nhận.</Muted>}
          <ul className="space-y-2">
            {(data.recent_activities ?? []).map((a) => (
              <li key={a.id} className="rounded-control border border-line px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-x-2 text-label text-ink-soft">
                  <span>{formatDateTime(a.occurred_at)}</span>
                  <span>· {CHANNEL_LABEL[a.channel]}</span>
                  {a.outcome && <span>· {OUTCOME_LABEL[a.outcome]}</span>}
                  {a.actor_name && <span>· {a.actor_name}</span>}
                </div>
                <p className="mt-0.5 text-small break-words text-ink">{a.note}</p>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Hội thoại">
          {(data.conversations ?? []).length === 0 && <Muted>Chưa có hội thoại.</Muted>}
          <ul className="space-y-2">
            {(data.conversations ?? []).map((c) => (
              <li key={c.id}>
                <Link
                  href={`/inbox?c=${c.id}`}
                  className="block rounded-control border border-line px-3 py-2.5 hover:bg-tile/50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-label text-ink-soft">
                      {formatDateTime(c.last_message_at)}
                    </span>
                    <Badge tone="gray" dot={false}>
                      {CONVERSATION_STATUS_LABEL[c.status]}
                    </Badge>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-small text-ink">
                    {c.last_message_preview}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Đồng ý của khách">
          {(data.consents ?? []).length === 0 && <Muted>Chưa ghi nhận đồng ý nào.</Muted>}
          <ul className="space-y-2">
            {(data.consents ?? []).map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 text-small">
                <span className="text-ink">{CONSENT_KIND_LABEL[c.kind]}</span>
                <Badge tone={c.granted ? "green" : "gray"} dot={false}>
                  {c.granted ? "Đã đồng ý" : "Chưa đồng ý"}
                </Badge>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-label text-ink-soft">
            Đồng ý hình ảnh và tin quảng bá được kiểm tra trước khi hệ thống chuẩn bị tin cho khách.
          </p>
        </Card>

        <Card title="Dòng thời gian">
          {(data.timeline ?? []).length === 0 && <Muted>Chưa có sự kiện.</Muted>}
          <ol className="ml-1.5 space-y-3 border-l border-line pl-4">
            {(data.timeline ?? []).slice(0, 8).map((ev) => (
              <li key={ev.id} className="relative">
                <span className="absolute top-1.5 -left-[21px] h-2 w-2 rounded-pill bg-brand-400" />
                <div className="text-label text-ink-soft">{formatDateTime(ev.at)}</div>
                <div className="text-small font-medium text-ink">{ev.title}</div>
                {ev.detail && <div className="text-label text-ink-soft">{ev.detail}</div>}
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <p className="text-label text-ink-soft">
        Patient 360 chỉ tổng hợp ngữ cảnh để xem nhanh. Hồ sơ, lịch và liệu trình gốc vẫn là nguồn
        sự thật.
      </p>
    </div>
  );
}
