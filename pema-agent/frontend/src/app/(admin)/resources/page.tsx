"use client";

// Bác sĩ & phòng: the doctors (account, shift and the load of a chosen day), the treatment rooms and the room
// blocks (`GET /api/v1/resources?day=`, `POST/PATCH /api/v1/rooms`, `POST/DELETE /api/v1/room-blocks`).
// Old web: `operations-ui.js` `resources()`. Differences, on purpose: a doctor is a staff account and the shift is
// the weekly shift of its account (set outside this screen), so nothing is typed twice here; rooms and blocks
// are new tables. Everyone who sees the schedule reads; the owner and the manager (`admin.rules`) change rooms and
// blocks. Layout: 1 column on a phone, 2 from `sm`, 3 from 1280, 4 from 1600.
import Link from "next/link";
import { useCallback, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconPlus } from "@/components/admin/shared/dashboard-icons";
import { BlockSheet, RoomSheet } from "@/components/catalog/room-sheets";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { Field } from "@/ui/field";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  breakLabel,
  catalogErrorMessage,
  loadLine,
  loadPercent,
  shiftLabel,
  type BlockRow,
  type DoctorRow,
  type RoomRow,
} from "@/lib/catalog/catalog-view";
import { clinicDateKey, formatDate } from "@/lib/ops/format";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { FIELD_CONTROL_CLASS } from "@/ui/field";
import { IconStethoscope } from "@/ui/icons";
import { Workspace } from "@/ui/workspace";

function DoctorCard({ doctor, day }: { doctor: DoctorRow; day: string }) {
  const percent = loadPercent(doctor.booked_minutes, doctor.shift_minutes);
  const pause = breakLabel(doctor.shift);
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <span
          aria-hidden
          className="grid h-11 w-11 place-items-center rounded-tile bg-brand-50 text-brand-500"
        >
          <IconStethoscope size={22} />
        </span>
        {!doctor.active && <Badge tone="warning">Tài khoản đã khóa</Badge>}
      </div>
      <h2 className="mt-3 text-subtitle font-bold text-heading">{doctor.name}</h2>
      <p className="text-small text-ink-soft">Da liễu · lịch ngày {formatDate(day)}</p>
      <div className="mt-5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-small font-semibold text-ink">
        <span>{shiftLabel(doctor.shift)}</span>
        {pause && <span className="text-label font-normal text-ink-soft">{pause}</span>}
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-pill bg-tile"
        role="progressbar"
        aria-label={`Tải lịch của ${doctor.name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div className="h-full rounded-pill bg-brand-500" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-2 text-label text-ink-soft">{loadLine(doctor)}</p>
      {!doctor.has_shift && (
        <p className="mt-2 text-label text-warning">Chưa thiết lập ca làm việc.</p>
      )}
      <div className="mt-5">
        <Link
          href={`/schedule?doctor=${doctor.user_id}`}
          // The schedule page is built by another step; no prefetch, so a missing page is not requested on load.
          prefetch={false}
          className={buttonClass("secondary")}
          aria-label={`Xem lịch bác sĩ ${doctor.name}`}
        >
          Xem lịch bác sĩ
        </Link>
      </div>
    </Card>
  );
}

function RoomCard({
  room,
  canManage,
  onEdit,
}: {
  room: RoomRow;
  canManage: boolean;
  onEdit: () => void;
}) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-body-lg font-bold text-heading">{room.name}</h3>
        <Badge tone={room.active ? "success" : "warning"}>
          {room.active ? "Đang dùng" : "Tạm ngưng"}
        </Badge>
      </div>
      <p className="mt-1 text-small text-ink-soft">Sức chứa {room.capacity} người</p>
      {canManage && (
        <div className="mt-4">
          <Button variant="secondary" onClick={onEdit} aria-label={`Sửa phòng ${room.name}`}>
            Sửa phòng
          </Button>
        </div>
      )}
    </Card>
  );
}

export default function ResourcesPage() {
  const { can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const canManage = can("admin.rules");
  const [day, setDay] = useState(() => clinicDateKey());
  const [editingRoom, setEditingRoom] = useState<RoomRow | "new" | null>(null);
  const [blocking, setBlocking] = useState(false);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(http.GET("/api/v1/resources", { params: { query: { day } }, signal })),
    [day],
  );
  const { data, error, loading, reload } = useLoad(load);

  const closeAll = useCallback(() => {
    setEditingRoom(null);
    setBlocking(false);
  }, []);
  const saved = useCallback(() => {
    closeAll();
    reload();
  }, [closeAll, reload]);

  async function removeBlock(block: BlockRow, roomName: string) {
    const ok = await confirm({
      title: "Gỡ khóa phòng?",
      message: `Phòng ${roomName} sẽ đặt lịch được lại trong khoảng ${block.start}–${block.end} ngày ${formatDate(block.day)}.`,
      confirmLabel: "Gỡ khóa",
      tone: "normal",
    });
    if (!ok) return;
    try {
      await unwrap(
        http.DELETE("/api/v1/room-blocks/{block_id}", {
          params: { path: { block_id: block.id } },
        }),
      );
      toast.push("success", "Đã gỡ khóa phòng.");
    } catch (e) {
      toast.push("error", catalogErrorMessage(e));
    }
    reload();
  }

  const roomName = (id: string) => data?.rooms.find((r) => r.id === id)?.name ?? "Phòng đã xóa";

  return (
    <div>
      <PageHeader
        title="Bác sĩ & phòng"
        subtitle="Ca làm việc và khoảng khóa được kiểm tra khi đặt hoặc dời lịch."
        aside={
          canManage ? (
            <PrimaryButton onClick={() => setBlocking(true)} disabled={!data}>
              <IconPlus size={16} />
              Khóa phòng
            </PrimaryButton>
          ) : undefined
        }
      />

      <div className="mb-4 max-w-xs">
        <Field label="Ngày xem tải lịch">
          {(control) => (
            <input
              {...control}
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value || clinicDateKey())}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={4} />}
      {data && data.doctors.length === 0 && (
        <EmptyState
          title="Chưa có bác sĩ nào"
          hint="Bác sĩ là tài khoản nhân viên có vai trò Bác sĩ."
        />
      )}
      {data && data.doctors.length > 0 && (
        <Workspace layout="cards" className="mb-6">
          {data.doctors.map((doctor) => (
            <DoctorCard key={doctor.user_id} doctor={doctor} day={data.day} />
          ))}
        </Workspace>
      )}

      {data && (
        <div className="mb-6">
          <Card
            title="Phòng điều trị"
            subtitle="Dịch vụ chọn phòng dùng được; phòng tạm ngưng không đặt lịch mới."
            aside={
              canManage ? (
                <Button variant="secondary" onClick={() => setEditingRoom("new")}>
                  <IconPlus size={16} />
                  Thêm phòng
                </Button>
              ) : undefined
            }
          >
            <Workspace layout="cards">
              {data.rooms.map((room) => (
                <RoomCard
                  key={room.id}
                  room={room}
                  canManage={canManage}
                  onEdit={() => setEditingRoom(room)}
                />
              ))}
            </Workspace>
            {data.rooms.length === 0 && (
              <p className="text-small text-ink-soft">Chưa có phòng nào.</p>
            )}
          </Card>
        </div>
      )}

      {data && (
        <Card
          title="Khoảng khóa phòng"
          subtitle={`Từ ngày ${formatDate(data.day)} trở đi. Khóa phòng khi bảo trì thiết bị hoặc nghỉ chuyên môn.`}
        >
          {data.blocks.length === 0 ? (
            <p className="text-small text-ink-soft">Không có khoảng khóa.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-body">
                <thead>
                  <tr className="border-b border-line text-label text-ink-soft">
                    <th className="py-2 pr-3 font-semibold">Phòng</th>
                    <th className="py-2 pr-3 font-semibold">Ngày</th>
                    <th className="py-2 pr-3 font-semibold">Thời gian</th>
                    <th className="py-2 pr-3 font-semibold">Lý do</th>
                    {canManage && <th className="py-2 font-semibold">Thao tác</th>}
                  </tr>
                </thead>
                <tbody>
                  {data.blocks.map((block) => (
                    <tr key={block.id} className="border-b border-line last:border-0">
                      <td className="py-2.5 pr-3">{roomName(block.room_id)}</td>
                      <td className="py-2.5 pr-3 whitespace-nowrap">{formatDate(block.day)}</td>
                      <td className="py-2.5 pr-3 whitespace-nowrap tabular-nums">
                        {block.start}–{block.end}
                      </td>
                      <td className="py-2.5 pr-3">{block.reason}</td>
                      {canManage && (
                        <td className="py-1.5">
                          <Button
                            variant="quiet"
                            onClick={() => void removeBlock(block, roomName(block.room_id))}
                            aria-label={`Gỡ khóa ${roomName(block.room_id)} ${block.start}`}
                          >
                            Gỡ khóa
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!canManage && (
            <div className="mt-3">
              <Notice>Chỉ chủ phòng khám và quản lý được thêm hoặc gỡ khóa phòng.</Notice>
            </div>
          )}
        </Card>
      )}

      {data && editingRoom !== null && (
        <RoomSheet
          room={editingRoom === "new" ? null : editingRoom}
          onClose={closeAll}
          onSaved={saved}
          onStale={reload}
        />
      )}
      {data && blocking && (
        <BlockSheet rooms={data.rooms} defaultDay={data.day} onClose={closeAll} onSaved={saved} />
      )}
      {confirmDialog}
    </div>
  );
}
