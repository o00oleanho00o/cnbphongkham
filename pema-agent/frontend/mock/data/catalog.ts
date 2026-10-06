// Fictional catalog for the configuration screens (services with versioned terms, rooms, room blocks, the
// laser-co2 protocol). Same sample catalog as the prototype (`operations-data.js`, `finance_server.py`); prices
// and rates are SYNTHETIC, not the clinic's real price list. Mirrors `pema.clinic.actions.catalog_seed`.
import { DAY, isoFromNow, uuid, type Schemas } from "../core";

type S = Schemas;

export const ROOM_IDS = [uuid(1, 21), uuid(2, 21), uuid(3, 21), uuid(4, 21)] as const;

export const rooms: S["RoomOut"][] = [
  { id: ROOM_IDS[0], name: "Khám da liễu", capacity: 1, active: true, version: 1 },
  { id: ROOM_IDS[1], name: "Tư vấn chuyên sâu", capacity: 1, active: true, version: 1 },
  { id: ROOM_IDS[2], name: "Laser & thủ thuật", capacity: 1, active: true, version: 1 },
  { id: ROOM_IDS[3], name: "Chăm sóc da", capacity: 1, active: true, version: 1 },
];

type Terms = {
  version_no: number;
  price_vnd: number;
  rate_bp: number;
  basis: S["ServiceBasis"];
  duration_min: number;
  buffer_min: number;
  changed_by: string | null;
  created_at: string;
};

export type ServiceRecord = {
  id: string;
  code: string;
  name: string;
  active: boolean;
  protocol_code: string | null;
  room_ids: string[];
  terms_version: number;
  version: number;
  history: Terms[];
};

const OWNER_ID = uuid(1, 1);

function seed(
  n: number,
  code: string,
  name: string,
  price: number,
  rate: number,
  duration: number,
  buffer: number,
  roomIds: string[],
  protocol: string | null,
): ServiceRecord {
  return {
    id: uuid(n, 22),
    code,
    name,
    active: true,
    protocol_code: protocol,
    room_ids: roomIds,
    terms_version: 1,
    version: 1,
    history: [
      {
        version_no: 1,
        price_vnd: price,
        rate_bp: rate,
        basis: "net",
        duration_min: duration,
        buffer_min: buffer,
        changed_by: OWNER_ID,
        created_at: isoFromNow(-90 * DAY),
      },
    ],
  };
}

export const services: ServiceRecord[] = [
  seed(
    1,
    "follow-up-visit",
    "Tái khám & đánh giá",
    300_000,
    1000,
    30,
    0,
    [ROOM_IDS[0], ROOM_IDS[1]],
    null,
  ),
  seed(
    2,
    "dermatology-consult",
    "Tư vấn da liễu",
    500_000,
    1500,
    45,
    15,
    [ROOM_IDS[0], ROOM_IDS[1]],
    null,
  ),
  seed(3, "laser-co2", "Laser theo chỉ định", 2_500_000, 2000, 45, 15, [ROOM_IDS[2]], "laser-co2"),
  seed(4, "skin-care", "Chăm sóc theo chỉ định", 1_200_000, 1200, 45, 15, [ROOM_IDS[3]], null),
];

export const protocols: S["ProtocolOut"][] = [
  {
    id: uuid(1, 23),
    code: "laser-co2",
    name: "Laser CO2",
    milestones: [
      { rule_key: "d1", day: 1 },
      { rule_key: "d3", day: 3 },
      { rule_key: "d7", day: 7 },
    ],
    followup_days: 30,
    window_days: 45,
    active: true,
    version: 1,
  },
];

export type BlockRecord = S["RoomBlockOut"];

function tomorrow(): string {
  return isoFromNow(DAY).slice(0, 10);
}

export const blocks: BlockRecord[] = [
  {
    id: uuid(1, 24),
    room_id: ROOM_IDS[2],
    day: tomorrow(),
    start: "14:00",
    end: "15:00",
    reason: "Bảo trì thiết bị laser",
    created_by: OWNER_ID,
  },
];

/** Weekly shift of the mock doctors: the same every day, with the 12:00-13:00 break (package M's shape). */
export const DEFAULT_SHIFT: S["ShiftIntervalOut"][] = [
  { start: "08:00", end: "12:00" },
  { start: "13:00", end: "18:00" },
];
