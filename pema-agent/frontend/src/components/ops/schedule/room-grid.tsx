"use client";

// The room-column day grid of "Điều phối lịch" (old `schedule()` of operations-ui.js): a time axis from 08:00 to
// 18:00 in half hours, one column per room, a card for every visit that holds the room and a hatched strip for
// every block ("Bảo trì thiết bị laser"). An empty half hour is a button "Đặt lịch <phòng> <giờ>" that opens the
// booking sheet with that room and start. The old board also let a card be dragged onto a slot; that is a mouse
// only shortcut (the dialog does the same), so it is not built here: open the card and change room or time.
// The grid scrolls inside its own frame, so the page never scrolls sideways. Visits with no room are listed
// under the grid. Every rule (busy room, block, hours) is the BE's.
import type { Schemas } from "@/lib/api";
import { AppointmentCard } from "@/components/ops/schedule/appointment-card";
import {
  GRID_HEIGHT_PX,
  SLOT_PX,
  SLOT_STARTS,
  blockBox,
  blockRange,
  bookingBox,
  roomColumns,
  withoutRoom,
} from "@/lib/ops/room-grid-view";
import { quickAction, type ScheduleAction, type ScheduleItem } from "@/lib/ops/schedule-view";
import type { Permission } from "@/lib/session/session-context";
import { Card } from "@/ui/card";

type Room = Schemas["RoomOut"];
type RoomBlock = Schemas["RoomBlockOut"];

const HEADER_PX = 52;

export function RoomGrid({
  day,
  items,
  rooms,
  blocks,
  can,
  busyId,
  onOpen,
  onQuick,
  onBookSlot,
}: {
  day: string;
  items: readonly ScheduleItem[];
  rooms: readonly Room[];
  blocks: readonly RoomBlock[];
  can: (permission: Permission) => boolean;
  busyId: string | null;
  onOpen: (item: ScheduleItem) => void;
  onQuick: (item: ScheduleItem, action: ScheduleAction) => void;
  /** Called with the room and the start of the empty half hour that was clicked; absent = read only. */
  onBookSlot?: (room: Room, clock: string) => void;
}) {
  const columns = roomColumns(rooms, items, blocks, day);
  const loose = withoutRoom(items, rooms);

  if (columns.length === 0) {
    return (
      <Card title="Theo phòng">
        <p className="text-label text-ink-soft">
          Chưa có phòng nào. Thêm phòng ở mục Bác sĩ &amp; phòng.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div
        className="overflow-x-auto rounded-card border border-line bg-surface shadow-card"
        role="region"
        aria-label="Lưới lịch theo phòng"
      >
        <div
          className="grid"
          style={{
            gridTemplateColumns: `56px repeat(${columns.length}, minmax(174px, 1fr))`,
            minWidth: 56 + columns.length * 174,
          }}
        >
          <div
            className="sticky left-0 z-20 border-r border-b border-line bg-surface px-2 py-3 text-micro font-semibold tracking-wider text-ink-soft uppercase"
            style={{ height: HEADER_PX }}
          >
            Giờ
          </div>
          {columns.map(({ room, items: roomItems }) => (
            <div
              key={room.id}
              className="border-b border-l border-line bg-surface px-3 py-2"
              style={{ height: HEADER_PX }}
            >
              <div className="truncate text-label font-bold text-heading">{room.name}</div>
              <div className="text-micro text-ink-soft">
                {roomItems.length} lịch{room.active ? "" : " · tạm ngưng"}
              </div>
            </div>
          ))}

          <div
            className="sticky left-0 z-10 border-r border-line bg-surface"
            style={{ height: GRID_HEIGHT_PX }}
            aria-hidden
          >
            {SLOT_STARTS.map((clock) => (
              <div
                key={clock}
                className="px-2 pt-0.5 text-micro text-ink-soft tabular-nums"
                style={{ height: SLOT_PX }}
              >
                {clock.endsWith(":00") ? clock : ""}
              </div>
            ))}
          </div>

          {columns.map(({ room, items: roomItems, blocks: roomBlocks }) => (
            <div
              key={room.id}
              className="relative border-l border-line"
              style={{ height: GRID_HEIGHT_PX }}
              data-room={room.id}
            >
              {SLOT_STARTS.map((clock) => (
                <div key={clock} className="border-b border-line/60" style={{ height: SLOT_PX }}>
                  {onBookSlot !== undefined && room.active && (
                    <button
                      type="button"
                      aria-label={`Đặt lịch ${room.name} ${clock}`}
                      onClick={() => onBookSlot(room, clock)}
                      className="h-full w-full text-micro text-transparent hover:bg-brand-50 hover:text-brand-500 focus-visible:bg-brand-50 focus-visible:text-brand-500 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-500"
                    >
                      Đặt lịch
                    </button>
                  )}
                </div>
              ))}

              {roomBlocks.map((block) => {
                const box = blockBox(block);
                return (
                  <div
                    key={block.id}
                    className="absolute inset-x-1 z-10 overflow-hidden rounded-tile border border-warning-line bg-warning-soft px-1.5 py-1 text-micro text-warning"
                    style={{
                      top: box.top,
                      height: box.height,
                      backgroundImage:
                        "repeating-linear-gradient(135deg, transparent 0 6px, rgb(0 0 0 / 0.06) 6px 12px)",
                    }}
                    title={`Khóa phòng ${blockRange(block)}: ${block.reason}`}
                  >
                    <strong className="block truncate">Khóa {blockRange(block)}</strong>
                    <span className="block truncate">{block.reason}</span>
                  </div>
                );
              })}

              {roomItems.map((item) => {
                const box = bookingBox(item);
                return (
                  <div
                    key={item.id}
                    className="absolute inset-x-1 z-10"
                    style={{ top: box.top + 1, height: box.height - 2 }}
                  >
                    <AppointmentCard
                      item={item}
                      compact
                      showDoctor={false}
                      showRoom={false}
                      quick={quickAction(item.status, can)}
                      busy={busyId === item.id}
                      onOpen={onOpen}
                      onQuick={onQuick}
                    />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {loose.length > 0 && (
        <Card
          title="Chưa xếp phòng"
          subtitle={`${loose.length} lịch chưa gắn phòng. Mở lịch để chọn phòng.`}
        >
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
            {loose.map((item) => (
              <AppointmentCard
                key={item.id}
                item={item}
                showDoctor
                showRoom={false}
                quick={quickAction(item.status, can)}
                busy={busyId === item.id}
                onOpen={onOpen}
                onQuick={onQuick}
              />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
