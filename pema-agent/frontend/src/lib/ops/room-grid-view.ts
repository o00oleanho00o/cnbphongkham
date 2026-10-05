// Pure helpers of the room-column grid on "/schedule" (old `schedule()` of operations-ui.js: one column per
// room, half-hour rows from 08:00 to 18:00). The grid only DRAWS what the BE returns; the room rules (a block,
// a busy room, the 08:00-18:00 window) are the BE's `validate`, so a refused move ends in the BE's own sentence.
import type { Schemas } from "@/lib/api";
import { clockOf } from "@/lib/ops/schedule-view";
import type { ScheduleItem } from "@/lib/ops/schedule-view";

type Room = Schemas["RoomOut"];
type RoomBlock = Schemas["RoomBlockOut"];

export const GRID_START_MIN = 8 * 60;
export const GRID_END_MIN = 18 * 60;
export const SLOT_MIN = 30;
/** Height of one half hour. The old grid used 60px; 40px keeps the whole day on one screen of a laptop. */
export const SLOT_PX = 40;

export const minutesOfClock = (clock: string): number =>
  Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3, 5));

export const clockOfMinutes = (minutes: number): string =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** "08:00", "08:30", … "17:30": the start of every slot of the day. */
export const SLOT_STARTS: readonly string[] = Array.from(
  { length: (GRID_END_MIN - GRID_START_MIN) / SLOT_MIN },
  (_, i) => clockOfMinutes(GRID_START_MIN + i * SLOT_MIN),
);

export const GRID_HEIGHT_PX = SLOT_STARTS.length * SLOT_PX;

/** Vertical box of a visit or a block, clipped to the 08:00-18:00 window of the grid. */
export function boxOf(startClock: string, durationMin: number): { top: number; height: number } {
  const start = Math.max(GRID_START_MIN, minutesOfClock(startClock));
  const end = Math.min(GRID_END_MIN, minutesOfClock(startClock) + durationMin);
  return {
    top: ((start - GRID_START_MIN) / SLOT_MIN) * SLOT_PX,
    height: (Math.max(end - start, 5) / SLOT_MIN) * SLOT_PX,
  };
}

export type RoomColumn = { room: Room; items: ScheduleItem[]; blocks: RoomBlock[] };

/** One column per room (inactive rooms only when they still hold a visit or a block that day). */
export function roomColumns(
  rooms: readonly Room[],
  items: readonly ScheduleItem[],
  blocks: readonly RoomBlock[],
  day: string,
): RoomColumn[] {
  return rooms
    .map((room) => ({
      room,
      items: items.filter((it) => it.room_id === room.id),
      blocks: blocks.filter((b) => b.room_id === room.id && b.day === day),
    }))
    .filter((column) => column.room.active || column.items.length > 0 || column.blocks.length > 0);
}

/** Visits of the day that no room holds (every visit made before rooms existed, or booked without one). */
export function withoutRoom(
  items: readonly ScheduleItem[],
  rooms: readonly Room[],
): ScheduleItem[] {
  const known = new Set(rooms.map((r) => r.id));
  return items.filter(
    (it) => it.room_id === null || it.room_id === undefined || !known.has(it.room_id),
  );
}

/** "08:30–09:15" of a block, as stored. */
export const blockRange = (block: RoomBlock): string => `${block.start}–${block.end}`;

export const bookingBox = (item: ScheduleItem) => boxOf(clockOf(item.starts_at), item.duration_min);

export const blockBox = (block: RoomBlock) =>
  boxOf(block.start, minutesOfClock(block.end) - minutesOfClock(block.start));
