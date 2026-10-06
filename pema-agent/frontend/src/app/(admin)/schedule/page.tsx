"use client";

// "Điều phối lịch": the clinic board for one day or seven days, with the reception status flow
// (Đặt hẹn, Đã xác nhận, Đang chờ, Đang điều trị, Hoàn tất; Vắng hẹn and Đã hủy close a visit). Behaviour source:
// prototype/shared/operations-ui.js (`schedule`) and crm-automation.js (`reception`); data from
// `GET /api/v1/appointments/schedule`, every change is a BE action (hours, double booking, who may do what).
// Two ways to read the day, switched by "Cột theo" and remembered per browser: doctor columns (the board of
// package U step U2) and room columns (the old half-hour grid with room blocks, step U10). Differences from the
// old board, on purpose: no service colours or waiting list, no drag to move (open the card and change the room
// or the time). On a phone the board is one list per day. Several people work the same board: an `appointments.changed`
// event reloads it quietly, the open sheet and the filters stay as they are.
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { BlockSheet } from "@/components/catalog/room-sheets";
import { AppointmentCard } from "@/components/ops/schedule/appointment-card";
import { AppointmentSheet, type SheetTarget } from "@/components/ops/schedule/appointment-sheet";
import { RoomGrid } from "@/components/ops/schedule/room-grid";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { clinicDateKey, formatDate } from "@/lib/ops/format";
import { APPOINTMENT_STATUS_LABEL } from "@/lib/ops/labels";
import { runTransition } from "@/lib/ops/schedule-api";
import {
  ACTION_DONE,
  STATUS_ORDER,
  addDays,
  dayLabel,
  groupByDay,
  groupByDoctor,
  isActive,
  isDayKey,
  quickAction,
  summarize,
  type ScheduleAction,
  type ScheduleItem,
} from "@/lib/ops/schedule-view";
import { usePatientIndex } from "@/lib/ops/use-patient-names";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { errorMessage } from "@/lib/api/client";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { FIELD_BASE_CLASS } from "@/ui/field";
import { Tile } from "@/ui/tile";

type View = Schemas["ScheduleView"];
type StatusFilter = Schemas["AppointmentStatus"] | "all";
type Columns = "doctor" | "room";

const COLUMNS_KEY = "pema.schedule.columns";
const COLUMNS_LABEL: Record<Columns, string> = { doctor: "Theo bác sĩ", room: "Theo phòng" };

/** The choice is per browser (not per account); storage can be blocked, then the doctor board is used. */
function readColumns(): Columns {
  try {
    return window.localStorage.getItem(COLUMNS_KEY) === "room" ? "room" : "doctor";
  } catch {
    return "doctor";
  }
}

function saveColumns(value: Columns): void {
  try {
    window.localStorage.setItem(COLUMNS_KEY, value);
  } catch {
    // private window or blocked storage: the choice just is not remembered
  }
}

const LIVE_TYPES: readonly LiveEventType[] = ["appointments.changed"];

export default function SchedulePage() {
  const { user, can } = useSession();
  const toast = useToast();
  const patients = usePatientIndex();
  const [day, setDay] = useState(() => clinicDateKey());
  const [view, setView] = useState<View>("day");
  const [doctorId, setDoctorId] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [showClosed, setShowClosed] = useState(false);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [columns, setColumns] = useState<Columns>("doctor");
  const [blocking, setBlocking] = useState(false);

  const ownBoard = user.role === "doctor";

  // The saved choice exists only in the browser (the server render has no storage), so it is read after mount.
  useEffect(() => {
    setColumns(readColumns());
  }, []);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/appointments/schedule", {
          params: {
            query: { day, view, doctor_id: doctorId === "" || ownBoard ? undefined : doctorId },
          },
          signal,
        }),
      ),
    [day, view, doctorId, ownBoard],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });

  const items = useMemo(() => data?.items ?? [], [data]);
  const doctors = useMemo(() => data?.doctors ?? [], [data]);
  const rooms = useMemo(() => data?.rooms ?? [], [data]);
  const blocks = useMemo(() => data?.blocks ?? [], [data]);
  const summary = useMemo(() => summarize(items), [items]);
  const visible = useMemo(
    () =>
      items.filter((it) =>
        status === "all" ? showClosed || isActive(it.status) : it.status === status,
      ),
    [items, status, showClosed],
  );

  const days = view === "week" ? 7 : 1;
  const mayWrite = can("appointment.write");
  const mayBlock = can("admin.rules");
  const roomView = columns === "room" && view === "day";

  const chooseColumns = (next: Columns) => {
    setColumns(next);
    saveColumns(next);
  };

  const changeDay = (next: string) => {
    if (isDayKey(next)) setDay(next);
  };
  const onSaved = useCallback(() => {
    setSheet(null);
    reload();
  }, [reload]);

  const onQuick = useCallback(
    async (item: ScheduleItem, action: ScheduleAction) => {
      setBusyId(item.id);
      try {
        await runTransition(action, item);
        toast.push("success", ACTION_DONE[action]);
        reload();
      } catch (err) {
        toast.push("error", errorMessage(err));
        reload();
      } finally {
        setBusyId(null);
      }
    },
    [toast, reload],
  );

  const renderCard = (item: ScheduleItem, showDoctor: boolean) => (
    <AppointmentCard
      key={item.id}
      item={item}
      showDoctor={showDoctor}
      quick={quickAction(item.status, can)}
      busy={busyId === item.id}
      onOpen={(it) => setSheet({ kind: "edit", item: it })}
      onQuick={(it, action) => void onQuick(it, action)}
    />
  );

  const newAppointmentFor = (forDay: string) =>
    setSheet({ kind: "create", day: forDay, doctorId: doctorId === "" ? null : doctorId });

  const subtitle =
    view === "week" ? `${formatDate(day)} – ${formatDate(addDays(day, 6))}` : formatDate(day);

  return (
    <div>
      <PageHeader
        title="Điều phối lịch"
        subtitle={`${subtitle} · ${data ? `${summary.total} lịch` : "đang tải"}`}
        aside={
          mayWrite ? <Button onClick={() => newAppointmentFor(day)}>＋ Đặt lịch</Button> : undefined
        }
      />

      <LiveStatus mode={liveMode} />

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Tile label="Lịch trong kỳ" value={summary.total} note="Theo bộ lọc đang chọn" />
        <Tile
          label="Thời gian điều trị"
          value={`${summary.treatmentMin}′`}
          note="Không gồm lịch hủy hoặc vắng"
        />
        <Tile
          label="Đang chờ"
          value={summary.waiting}
          note="Đã check-in, chưa vào điều trị"
          tone={summary.waiting > 0 ? "warning" : "neutral"}
        />
        <Tile label="Vắng / hủy" value={summary.closed} note="Đã giải phóng giờ hẹn" />
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <Button
            variant="secondary"
            aria-label="Ngày trước"
            onClick={() => setDay(addDays(day, -days))}
          >
            ←
          </Button>
          <label className="block text-label font-semibold text-ink-soft">
            Ngày bắt đầu
            <input
              type="date"
              value={day}
              onChange={(e) => changeDay(e.target.value)}
              className={`${FIELD_BASE_CLASS} mt-1 block w-44`}
            />
          </label>
          <Button
            variant="secondary"
            aria-label="Ngày tiếp theo"
            onClick={() => setDay(addDays(day, days))}
          >
            →
          </Button>
          <Button variant="secondary" onClick={() => setDay(clinicDateKey())}>
            Hôm nay
          </Button>
        </div>
        <div role="group" aria-label="Kiểu xem" className="flex gap-2">
          <FilterChip selected={view === "day"} onClick={() => setView("day")}>
            Ngày
          </FilterChip>
          <FilterChip selected={view === "week"} onClick={() => setView("week")}>
            7 ngày
          </FilterChip>
        </div>
        {view === "day" && (
          <div role="group" aria-label="Cột theo" className="flex gap-2">
            {(Object.keys(COLUMNS_LABEL) as Columns[]).map((key) => (
              <FilterChip key={key} selected={columns === key} onClick={() => chooseColumns(key)}>
                {COLUMNS_LABEL[key]}
              </FilterChip>
            ))}
          </div>
        )}
        {roomView && mayBlock && rooms.length > 0 && (
          <Button variant="secondary" onClick={() => setBlocking(true)}>
            ＋ Khóa phòng
          </Button>
        )}
        {!ownBoard && (
          <label className="block text-label font-semibold text-ink-soft">
            Bác sĩ
            <select
              value={doctorId}
              onChange={(e) => setDoctorId(e.target.value)}
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

      <div className="mb-4 space-y-3">
        <ChipRow label="Trạng thái">
          <FilterChip selected={status === "all"} onClick={() => setStatus("all")}>
            Tất cả
          </FilterChip>
          {STATUS_ORDER.map((s) => (
            <FilterChip
              key={s}
              selected={status === s}
              onClick={() => setStatus(s)}
              count={summary.byStatus[s]}
            >
              {APPOINTMENT_STATUS_LABEL[s]}
            </FilterChip>
          ))}
          {status === "all" && (
            <FilterChip selected={showClosed} onClick={() => setShowClosed((v) => !v)}>
              Hiện lịch hủy / vắng
            </FilterChip>
          )}
        </ChipRow>
      </div>

      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && data === undefined && <ListSkeleton rows={5} />}

      {data !== undefined && visible.length === 0 && !roomView && (
        <EmptyState
          title="Chưa có lịch hẹn"
          hint="Không có lịch nào khớp bộ lọc trong khoảng đã chọn."
        />
      )}

      {data !== undefined && roomView && (
        <RoomGrid
          day={day}
          items={visible}
          rooms={rooms}
          blocks={blocks}
          can={can}
          busyId={busyId}
          onOpen={(it) => setSheet({ kind: "edit", item: it })}
          onQuick={(it, action) => void onQuick(it, action)}
          onBookSlot={
            mayWrite
              ? (room, clock) =>
                  setSheet({
                    kind: "create",
                    day,
                    doctorId: doctorId === "" ? null : doctorId,
                    roomId: room.id,
                    clock,
                  })
              : undefined
          }
        />
      )}

      {data !== undefined && view === "day" && !roomView && visible.length > 0 && (
        <DayBoard
          items={visible}
          doctors={doctors}
          groupByDoctors={doctorId === "" && !ownBoard}
          renderCard={renderCard}
        />
      )}

      {data !== undefined && view === "week" && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4 wide:grid-cols-7">
          {groupByDay(visible, day, 7).map((column) => (
            <Card
              key={column.day}
              title={dayLabel(column.day)}
              subtitle={`${column.items.length} lịch`}
              aside={
                mayWrite ? (
                  <Button
                    variant="secondary"
                    className="min-h-9"
                    onClick={() => newAppointmentFor(column.day)}
                  >
                    ＋ Đặt lịch
                  </Button>
                ) : undefined
              }
            >
              <div className="space-y-2">
                {column.items.length === 0 && (
                  <p className="text-label text-ink-soft">Chưa có lịch</p>
                )}
                {column.items.map((item) => renderCard(item, true))}
              </div>
            </Card>
          ))}
        </div>
      )}

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

      {blocking && (
        <BlockSheet
          rooms={rooms}
          defaultDay={day}
          onClose={() => setBlocking(false)}
          onSaved={() => {
            setBlocking(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

/** The day: one column per doctor from `lg`, one list on a phone. A filter on one doctor is one column. */
function DayBoard({
  items,
  doctors,
  groupByDoctors,
  renderCard,
}: {
  items: readonly ScheduleItem[];
  doctors: readonly Schemas["ScheduleDoctor"][];
  groupByDoctors: boolean;
  renderCard: (item: ScheduleItem, showDoctor: boolean) => React.ReactNode;
}) {
  const columns = useMemo(
    () => groupByDoctor(items, doctors).filter((c) => c.items.length > 0),
    [items, doctors],
  );
  if (!groupByDoctors || columns.length <= 1) {
    return (
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((it) => renderCard(it, true))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3 wide:grid-cols-4">
      {columns.map((column) => (
        <Card
          key={column.id ?? "none"}
          title={column.name}
          subtitle={`${column.items.length} lịch`}
        >
          <div className="space-y-2">{column.items.map((item) => renderCard(item, false))}</div>
        </Card>
      ))}
    </div>
  );
}
