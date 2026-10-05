"use client";

// "Hôm nay tại Pema": the reception table of the old web (`today()` in prototype/shared/crm-ui.js), added above the
// CSKH task queue of "/today" (which stays as it is). Today's visits one row each: Giờ, Mã KH · bệnh nhân, Liên hệ,
// Nội dung, Trạng thái, Bác sĩ, Phòng, Người tạo and the buttons Check-in / Vắng / Mời vào phòng / Mở 360. The
// buttons call the same transitions as the board on "/schedule" (`POST /appointments/{id}/check-in|miss|start`), so
// the CRM events are the ones the board already emits. Eight tiles count the day and six of them filter; search by
// name, code or phone; paging of 25. Below `md` the table becomes the card list of the board. The old "Giá lịch dự
// kiến" column and the money tile are not here: an appointment carries no price and no invoice in this system.
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { AppointmentCard } from "@/components/ops/schedule/appointment-card";
import { AppointmentSheet, type SheetTarget } from "@/components/ops/schedule/appointment-sheet";
import { useToast } from "@/components/ops/toast";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { clinicDateKey, formatDate } from "@/lib/ops/format";
import {
  PENDING_LABEL,
  RECEPTION_ACTION_LABEL,
  RECEPTION_PAGE_SIZE,
  RECEPTION_STATUS_LABEL,
  RECEPTION_STATUS_TONE,
  RECEPTION_TILES,
  ageLabel,
  filterReception,
  pageCount,
  pageOf,
  receptionActions,
  receptionCounts,
  type ReceptionStatusFilter,
} from "@/lib/ops/reception-view";
import { runTransition } from "@/lib/ops/schedule-api";
import {
  ACTION_DONE,
  quickAction,
  timeRange,
  type ScheduleAction,
  type ScheduleItem,
} from "@/lib/ops/schedule-view";
import { type PatientIndex } from "@/lib/ops/use-patient-names";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const LIVE_TYPES: readonly LiveEventType[] = ["appointments.changed"];

const STATUS_OPTIONS: readonly { value: ReceptionStatusFilter; label: string }[] = [
  { value: "all", label: "Tất cả trạng thái" },
  { value: "pending", label: PENDING_LABEL },
  ...(
    ["booked", "confirmed", "arrived", "in_progress", "completed", "cancelled", "missed"] as const
  ).map((value) => ({ value, label: RECEPTION_STATUS_LABEL[value] })),
];

export function ReceptionTable({ patients }: { patients: PatientIndex }) {
  const { user, can } = useSession();
  const toast = useToast();
  const [today] = useState(() => clinicDateKey());
  const [status, setStatus] = useState<ReceptionStatusFilter>("all");
  const [doctorId, setDoctorId] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const ownBoard = user.role === "doctor";
  const mayWrite = can("appointment.write");

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/appointments/schedule", {
          params: { query: { day: today, view: "day" } },
          signal,
        }),
      ),
    [today],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);
  useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });

  const items = useMemo(() => data?.items ?? [], [data]);
  const doctors = useMemo(() => data?.doctors ?? [], [data]);
  const rooms = useMemo(() => data?.rooms ?? [], [data]);
  const counts = useMemo(() => receptionCounts(items), [items]);

  const phoneOf = useCallback(
    (item: ScheduleItem) => patients.get(item.patient_id)?.phone ?? "",
    [patients],
  );
  const rows = useMemo(
    () => filterReception(items, { status, doctorId, query }, phoneOf),
    [items, status, doctorId, query, phoneOf],
  );
  const pages = pageCount(rows.length);
  const safePage = Math.min(page, pages);
  const shown = useMemo(() => pageOf(rows, safePage), [rows, safePage]);

  const changeFilter =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setPage(1);
    };

  const onAction = useCallback(
    async (item: ScheduleItem, action: ScheduleAction) => {
      setBusyId(item.id);
      try {
        await runTransition(action, item);
        toast.push("success", ACTION_DONE[action]);
      } catch (err) {
        toast.push("error", errorMessage(err));
      } finally {
        setBusyId(null);
        reload();
      }
    },
    [toast, reload],
  );

  const onSaved = useCallback(() => {
    setSheet(null);
    reload();
  }, [reload]);

  return (
    <section aria-label="Tiếp đón hôm nay" className="mb-8">
      <Card
        title="Hôm nay tại Pema"
        subtitle={`Tiếp đón theo từng lịch hẹn · ${formatDate(today)}`}
        aside={
          mayWrite ? (
            <Button onClick={() => setSheet({ kind: "create", day: today, doctorId: null })}>
              ＋ Đặt lịch mới
            </Button>
          ) : undefined
        }
      >
        <div
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8"
          aria-label="Thống kê tiếp đón"
        >
          <StatCell label="Tổng lịch" value={counts.total} />
          <StatCell label="Đã đến" value={counts.came} />
          {RECEPTION_TILES.map((tile) => (
            <button
              key={tile.key}
              type="button"
              aria-pressed={status === tile.key}
              onClick={() => changeFilter(setStatus)(status === tile.key ? "all" : tile.key)}
              className={cx(
                "min-w-0 rounded-tile border px-3 py-2 text-left transition-colors hover:bg-tile",
                status === tile.key ? "border-brand-500 bg-brand-50" : "border-line bg-surface",
              )}
            >
              <strong className="block text-body-lg text-heading">{counts.byTile[tile.key]}</strong>
              <span className="block truncate text-label text-ink-soft">{tile.label}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block text-label font-semibold text-ink-soft">
            Tên / mã KH / liên hệ
            <input
              type="search"
              value={query}
              placeholder="Tìm nhanh khách…"
              onChange={(e) => changeFilter(setQuery)(e.target.value)}
              className={`${FIELD_BASE_CLASS} mt-1 block w-60`}
            />
          </label>
          <label className="block text-label font-semibold text-ink-soft">
            Trạng thái
            <select
              value={status}
              // the options are the STATUS_OPTIONS values, nothing else can be selected
              onChange={(e) => changeFilter(setStatus)(e.target.value as ReceptionStatusFilter)}
              className={`${FIELD_BASE_CLASS} mt-1 block w-56`}
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {!ownBoard && (
            <label className="block text-label font-semibold text-ink-soft">
              Bác sĩ
              <select
                value={doctorId}
                onChange={(e) => changeFilter(setDoctorId)(e.target.value)}
                className={`${FIELD_BASE_CLASS} mt-1 block w-52`}
              >
                <option value="">Tất cả bác sĩ</option>
                {doctors.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div className="mt-4">
          {error !== "" && <RetryNotice message={error} onRetry={reload} />}
          {loading && data === undefined && <ListSkeleton rows={4} />}
          {data !== undefined && rows.length === 0 && (
            <EmptyState
              title="Không có lịch phù hợp."
              hint="Đổi bộ lọc trạng thái, bác sĩ hoặc từ khóa để xem các lịch khác trong ngày."
            />
          )}

          {rows.length > 0 && (
            <>
              <div className="hidden overflow-x-auto rounded-card border border-line md:block">
                <table className="w-full min-w-[860px] text-left text-body">
                  <thead>
                    <tr className="border-b border-line bg-table-head text-micro tracking-wider text-ink-soft uppercase">
                      <th className="px-3 py-2.5 font-semibold">Giờ</th>
                      <th className="px-3 py-2.5 font-semibold">Mã KH · bệnh nhân</th>
                      <th className="px-3 py-2.5 font-semibold">Liên hệ</th>
                      <th className="px-3 py-2.5 font-semibold">Nội dung</th>
                      <th className="px-3 py-2.5 font-semibold">Trạng thái</th>
                      <th className="px-3 py-2.5 font-semibold">Bác sĩ</th>
                      <th className="hidden px-3 py-2.5 font-semibold xl:table-cell">Phòng</th>
                      <th className="hidden px-3 py-2.5 font-semibold xl:table-cell">Người tạo</th>
                      <th className="px-3 py-2.5 font-semibold">Tiếp đón</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((item) => (
                      <ReceptionRow
                        key={item.id}
                        item={item}
                        patients={patients}
                        today={today}
                        busy={busyId === item.id}
                        onAction={onAction}
                      />
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="space-y-2 md:hidden">
                {shown.map((item) => (
                  <AppointmentCard
                    key={item.id}
                    item={item}
                    showDoctor
                    quick={quickAction(item.status, can)}
                    busy={busyId === item.id}
                    onOpen={(it) => setSheet({ kind: "edit", item: it })}
                    onQuick={(it, action) => void onAction(it, action)}
                  />
                ))}
              </div>
            </>
          )}

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-label text-ink-soft">
              {rows.length} lịch · Trang {safePage}/{pages} · {RECEPTION_PAGE_SIZE} dòng/trang
            </span>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                className="min-h-9"
                disabled={safePage <= 1}
                onClick={() => setPage(safePage - 1)}
              >
                ← Trước
              </Button>
              <Button
                variant="secondary"
                className="min-h-9"
                disabled={safePage >= pages}
                onClick={() => setPage(safePage + 1)}
              >
                Sau →
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {sheet !== null && (
        <AppointmentSheet
          target={sheet}
          doctors={doctors}
          rooms={rooms}
          patients={patients}
          onClose={() => setSheet(null)}
          onSaved={onSaved}
        />
      )}
    </section>
  );
}

function StatCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0 rounded-tile border border-line bg-surface px-3 py-2">
      <strong className="block text-body-lg text-heading">{value}</strong>
      <span className="block truncate text-label text-ink-soft">{label}</span>
    </div>
  );
}

function ReceptionRow({
  item,
  patients,
  today,
  busy,
  onAction,
}: {
  item: ScheduleItem;
  patients: PatientIndex;
  today: string;
  busy: boolean;
  onAction: (item: ScheduleItem, action: ScheduleAction) => Promise<void>;
}) {
  const { can } = useSession();
  const patient = patients.get(item.patient_id);
  const name = item.patient_name ?? patient?.full_name ?? item.patient_code;
  const actions = receptionActions(item.status, can);
  const open360 = actions.length === 0 && can("patient.read_360");
  return (
    <tr className="border-b border-line/60 align-top last:border-0 hover:bg-tile/40">
      <td
        className="px-3 py-2.5 font-bold tabular-nums"
        title={timeRange(item.starts_at, item.duration_min)}
      >
        {item.starts_at.slice(11, 16)}
      </td>
      <td className="px-3 py-2.5">
        {can("patient.read_360") ? (
          <Link
            href={`/patients/${item.patient_id}`}
            className="font-semibold text-link hover:underline"
          >
            {name}
          </Link>
        ) : (
          <span className="font-semibold text-heading">{name}</span>
        )}
        <small className="block text-label text-ink-soft">{item.patient_code}</small>
      </td>
      <td className="px-3 py-2.5">
        {patient?.phone ?? "—"}
        <small className="block text-label text-ink-soft">
          {ageLabel(patient?.birth_date, today)}
        </small>
      </td>
      <td className="px-3 py-2.5">{item.note ?? "Không ghi chú"}</td>
      <td className="px-3 py-2.5">
        <Badge tone={RECEPTION_STATUS_TONE[item.status]}>
          {RECEPTION_STATUS_LABEL[item.status]}
        </Badge>
      </td>
      <td className="px-3 py-2.5">{item.doctor_name ?? "Chưa gán bác sĩ"}</td>
      <td className="hidden px-3 py-2.5 xl:table-cell">{item.room_name ?? "—"}</td>
      <td className="hidden px-3 py-2.5 xl:table-cell">{item.created_by_name ?? "—"}</td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap gap-2">
          {actions.map((action, index) => (
            <Button
              key={action}
              variant={index === 0 ? "primary" : "secondary"}
              className="min-h-9"
              disabled={busy}
              onClick={() => void onAction(item, action)}
            >
              {RECEPTION_ACTION_LABEL[action]}
            </Button>
          ))}
          {open360 && (
            <Link
              href={`/patients/${item.patient_id}`}
              className="inline-flex min-h-9 items-center rounded-control border border-line-strong px-3 text-body font-semibold text-ink hover:bg-tile"
            >
              Mở 360
            </Link>
          )}
        </div>
      </td>
    </tr>
  );
}
