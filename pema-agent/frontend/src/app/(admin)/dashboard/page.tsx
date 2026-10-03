"use client";

// "Tổng quan": the KPIs of the clinic for today, this week or this month. Behaviour source:
// prototype/shared/crm-ui.js `dashboard()` and `doctorHome()`; the numbers come from `GET /api/v1/dashboard/kpis`.
// A number appears only when the BE could compute it from stored rows: there is no revenue tile (money needs the
// cashier and finance data of later steps), no "customers at risk" or lifecycle stages (the rules engine derives
// them per run, they are not rows). A rate with nothing to divide by shows a dash. A doctor sees their own visits.
import Link from "next/link";
import { useCallback, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { ChipRow, FilterChip, ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { http, unwrap } from "@/lib/api/client";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import {
  RANGES,
  RANGE_LABEL,
  barWidth,
  percentLabel,
  spanLabel,
  type DashboardRange,
} from "@/lib/ops/dashboard-view";
import { APPOINTMENT_STATUS_LABEL } from "@/lib/ops/labels";
import { STATUS_TONE } from "@/lib/ops/schedule-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { Tile } from "@/ui/tile";
import type { Schemas } from "@/lib/api";

type Appointments = Schemas["AppointmentKpis"];

const LIVE_TYPES: readonly LiveEventType[] = ["appointments.changed", "tasks.changed"];

/** Statuses of the breakdown, in the order of the visit. */
const BREAKDOWN: readonly {
  status: Schemas["AppointmentStatus"];
  value: (a: Appointments) => number;
}[] = [
  { status: "booked", value: (a) => a.upcoming },
  { status: "arrived", value: (a) => a.waiting },
  { status: "in_progress", value: (a) => a.in_progress },
  { status: "completed", value: (a) => a.completed },
  { status: "missed", value: (a) => a.missed },
  { status: "cancelled", value: (a) => a.cancelled },
];

export default function DashboardPage() {
  const { user, can } = useSession();
  const [range, setRange] = useState<DashboardRange>("today");

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(http.GET("/api/v1/dashboard/kpis", { params: { query: { range } }, signal })),
    [range],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });

  const own = data?.scope === "doctor";
  const title = user.role === "doctor" ? "Không gian bác sĩ" : "Tổng quan";
  const subtitle = data
    ? `${RANGE_LABEL[range]} · ${spanLabel(data.starts_on, data.ends_on)}`
    : RANGE_LABEL[range];

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={subtitle}
        aside={
          can("appointment.read") ? (
            <Link href="/schedule" className={buttonClass("secondary")}>
              Mở điều phối lịch →
            </Link>
          ) : undefined
        }
      />

      <LiveStatus mode={liveMode} />

      <div className="mb-4">
        <ChipRow label="Khoảng thời gian">
          {RANGES.map((r) => (
            <FilterChip key={r} selected={range === r} onClick={() => setRange(r)}>
              {RANGE_LABEL[r]}
            </FilterChip>
          ))}
        </ChipRow>
      </div>

      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && data === undefined && <ListSkeleton rows={4} />}

      {data !== undefined && own && (
        <div className="mb-4">
          <Notice>Chỉ gồm lịch của bạn và việc chăm sóc thuộc hồ sơ bạn phụ trách.</Notice>
        </div>
      )}

      {data?.appointments && data.patients && (
        <section aria-label="Vận hành" className="mb-5">
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <Tile
              label="Lịch trong kỳ"
              value={data.appointments.total}
              note={`${data.appointments.upcoming} chưa đến`}
            />
            <Tile
              label="Đã đến / đang chờ"
              value={
                <>
                  {data.appointments.visits}{" "}
                  <small className="text-body-lg text-ink-soft">
                    / {data.appointments.waiting}
                  </small>
                </>
              }
              note="Check-in, đang điều trị, hoàn tất"
              tone={data.appointments.waiting > 0 ? "warning" : "neutral"}
            />
            <Tile
              label="Vắng hẹn"
              value={data.appointments.missed}
              note={`${data.appointments.cancelled} lịch đã hủy`}
              tone={data.appointments.missed > 0 ? "danger" : "neutral"}
            />
            <Tile
              label="Bệnh nhân đã khám"
              value={data.patients.seen}
              note={`${data.patients.new} mới · ${data.patients.returning} quay lại`}
            />
          </div>
        </section>
      )}

      {data?.care && (
        <section aria-label="Chăm sóc khách hàng" className="mb-5">
          <h2 className="mb-2 text-body-lg font-bold text-heading">Chăm sóc khách hàng</h2>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <Tile
              label="Việc đến hạn"
              value={data.care.tasks_due}
              note={`${data.care.tasks_resolved} đã xử lý`}
            />
            <Tile
              label="Hoàn tất chăm sóc"
              value={percentLabel(data.care.followup_completion_pct)}
              note="Việc đến hạn trong kỳ đã xử lý"
            />
            <Tile
              label="Việc quá hạn"
              value={data.care.overdue_tasks}
              note={`${data.care.overdue_patients} khách cần hỗ trợ`}
              tone={data.care.overdue_tasks > 0 ? "danger" : "neutral"}
            />
            <Tile
              label="Liên hệ thành công"
              value={percentLabel(data.care.contact_rate_pct)}
              note={`${data.care.contacts_reached}/${data.care.contact_attempts} lần liên hệ`}
            />
            <Tile
              label="Lịch đặt sau CSKH"
              value={data.care.booked_after_care}
              note="Khách đặt lịch chưa được tính là đã quay lại"
            />
          </div>
          {can("crm.task.read") && (
            <p className="mt-2 text-label">
              <Link href="/today" className="font-medium text-link hover:underline">
                Mở việc hôm nay →
              </Link>
            </p>
          )}
        </section>
      )}

      {data?.appointments && <StatusBreakdown appointments={data.appointments} />}

      {data !== undefined && (
        <p className="mt-4 text-label text-ink-soft">
          Chưa có số doanh thu trên màn này: cần dữ liệu hóa đơn từ Thu ngân và Tài chính.
        </p>
      )}
    </div>
  );
}

function StatusBreakdown({ appointments }: { appointments: Appointments }) {
  return (
    <Card
      title="Lịch hẹn theo trạng thái"
      subtitle="Trạng thái hiện tại của các lịch bắt đầu trong kỳ"
    >
      <ul className="space-y-2.5">
        {BREAKDOWN.map(({ status, value }) => {
          const count = value(appointments);
          return (
            <li
              key={status}
              className="grid grid-cols-[8.5rem_minmax(0,1fr)_2.5rem] items-center gap-3"
            >
              <Badge tone={STATUS_TONE[status]}>
                {status === "booked" ? "Chưa đến" : APPOINTMENT_STATUS_LABEL[status]}
              </Badge>
              <span aria-hidden className="h-2 overflow-hidden rounded-pill bg-tile">
                <span
                  className="block h-full rounded-pill bg-brand-500"
                  style={{ width: barWidth(count, appointments.total) }}
                />
              </span>
              <span className="text-right text-body font-semibold text-heading tabular-nums">
                {count}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
