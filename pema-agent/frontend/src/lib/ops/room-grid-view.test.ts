import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import {
  GRID_HEIGHT_PX,
  SLOT_PX,
  SLOT_STARTS,
  blockBox,
  boxOf,
  clockOfMinutes,
  roomColumns,
  withoutRoom,
} from "./room-grid-view";
import type { ScheduleItem } from "./schedule-view";

const ROOMS: Schemas["RoomOut"][] = [
  { id: "r-1", name: "Khám da liễu", capacity: 1, active: true, version: 1 },
  { id: "r-2", name: "Laser", capacity: 1, active: false, version: 1 },
];

function visit(over: Partial<ScheduleItem>): ScheduleItem {
  return {
    id: "a-1",
    patient_id: "p-1",
    patient_code: "P001",
    doctor_id: null,
    starts_at: "2026-09-20T09:00:00+07:00",
    duration_min: 30,
    status: "booked",
    version: 1,
    ...over,
  };
}

describe("the time axis", () => {
  it("has_20_half_hour_slots_from_0800_to_1730", () => {
    expect(SLOT_STARTS).toHaveLength(20);
    expect(SLOT_STARTS[0]).toBe("08:00");
    expect(SLOT_STARTS.at(-1)).toBe("17:30");
    expect(GRID_HEIGHT_PX).toBe(20 * SLOT_PX);
    expect(clockOfMinutes(9 * 60 + 5)).toBe("09:05");
  });

  it("places_a_visit_by_start_and_length_and_clips_to_the_window", () => {
    expect(boxOf("08:00", 30)).toEqual({ top: 0, height: SLOT_PX });
    expect(boxOf("09:00", 45)).toEqual({ top: 2 * SLOT_PX, height: 1.5 * SLOT_PX });
    expect(boxOf("17:30", 60).height).toBe(SLOT_PX);
  });

  it("places_a_block_by_its_clock_window", () => {
    const block: Schemas["RoomBlockOut"] = {
      id: "b",
      room_id: "r-1",
      day: "2026-09-20",
      start: "14:00",
      end: "15:00",
      reason: "x",
    };
    expect(blockBox(block)).toEqual({ top: 12 * SLOT_PX, height: 2 * SLOT_PX });
  });
});

describe("room columns", () => {
  const block: Schemas["RoomBlockOut"] = {
    id: "b",
    room_id: "r-2",
    day: "2026-09-20",
    start: "14:00",
    end: "15:00",
    reason: "Bảo trì",
  };

  it("hides_a_paused_room_unless_it_still_holds_a_visit_or_a_block_that_day", () => {
    expect(roomColumns(ROOMS, [], [], "2026-09-20").map((c) => c.room.id)).toEqual(["r-1"]);
    expect(roomColumns(ROOMS, [], [block], "2026-09-20").map((c) => c.room.id)).toEqual([
      "r-1",
      "r-2",
    ]);
    expect(roomColumns(ROOMS, [], [block], "2026-09-21").map((c) => c.room.id)).toEqual(["r-1"]);
  });

  it("puts_each_visit_in_its_room_and_the_rest_apart", () => {
    const items = [
      visit({ id: "in", room_id: "r-1" }),
      visit({ id: "none" }),
      visit({ id: "gone", room_id: "r-9" }),
    ];
    expect(roomColumns(ROOMS, items, [], "2026-09-20")[0]?.items.map((i) => i.id)).toEqual(["in"]);
    expect(withoutRoom(items, ROOMS).map((i) => i.id)).toEqual(["none", "gone"]);
  });
});
