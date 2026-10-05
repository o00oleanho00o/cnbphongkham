// Product catalog and orders for the cashier screens. The products are fourteen ROWS OF THE CLINIC'S OWN PRICE LIST
// (`prototype/shared/product-catalog.json`, 115 rows, product id = the Excel code): real product data, the
// catalog is not synthetic. The full list is loaded into the real database by `pema catalog import`; the mock
// keeps a sample of it, with the same fields and the same rules for the sheet a code goes to (Thuốc is Đơn thuốc,
// any other type is Phiếu tư vấn, no type is "Cần phân loại"). Patients, doctors and the orders are fictional.
import { DOCTOR_AN, DOCTOR_MAI, DOCTOR_TAM, patientRef } from "./clinic";
import { uuid, isoFromNow, DAY, type Schemas } from "../core";

type S = Schemas;

export type ProductRecord = S["ProductOut"];

function product(
  code: string,
  name: string,
  unit: string,
  sourceType: string,
  price: number,
  vat: number,
  rowNumber: number,
): ProductRecord {
  const route: ProductRecord["route"] =
    sourceType === "" ? "UNRESOLVED" : sourceType === "Thuốc" ? "PRESCRIPTION" : "CONSULTATION";
  return {
    code,
    name,
    unit,
    source_type: sourceType,
    route,
    price_vnd: price,
    vat,
    row_number: rowNumber,
    active: true,
  };
}

export const products: ProductRecord[] = [
  product(
    "H002",
    "Desloratadine/Genepharm (Desloratadine 5 mg) Hộp 30 Viên - Viên - A",
    "Viên",
    "Thuốc",
    5500,
    0.05,
    2,
  ),
  product(
    "H005",
    "Cicaderm Cream 40ml - Kem làm mềm da, dưỡng ẩm, hỗ trợ làm đều màu da, mờ sẹo 40 ml - A",
    "Hộp",
    "Mỹ Phẩm",
    715000,
    0.08,
    3,
  ),
  product(
    "H006",
    "Heliocare Luminance Oral 60 Caps/ Viên uống sáng da - P",
    "Hộp",
    "TPCN",
    2808000,
    0.08,
    4,
  ),
  product(
    "H007",
    "Bio Phyto -1 Mild Facial Cleanser - Sữa rửa mặt làm sạch sâu 100ml - A",
    "Chai",
    "Mỹ Phẩm",
    660000,
    0.08,
    5,
  ),
  product("H008", "Kem trị mụn NV ACTIPUR 3 EN 1 CARE 30ML - P", "Hộp", "Mỹ Phẩm", 635000, 0.08, 6),
  product(
    "H010",
    "Bio Phyto -1 Mild Facial Cleanser - Sữa rửa mặt làm sạch sâu 500 ml - A",
    "Tuýp",
    "Mỹ Phẩm",
    2390000,
    0.08,
    7,
  ),
  product(
    "H012",
    "Dưỡng ẩm da dầu Floslek 50ml Mattifying Cream - O",
    "Hộp",
    "Mỹ Phẩm",
    650000,
    0.08,
    8,
  ),
  product(
    "H013",
    "Line Repair-Hydra-Theraskin+HA 50 serum dưỡng ẩm - P",
    "Hộp",
    "Mỹ Phẩm",
    1880000,
    0.08,
    9,
  ),
  product(
    "H014",
    "Tatopic 0.1% - Hộp 1 tuýp 10g thuốc mỡ bôi da - A",
    "Tuýp",
    "Thuốc",
    250000,
    0.05,
    10,
  ),
  product("H015", "Fogyma 5ml - A", "Ống", "Thuốc", 8750, 0.05, 11),
  product("H016", "Enzicoba- chống lão hóa, tăng miễn dịch - P", "Hộp", "Thuốc", 350000, 0.05, 12),
  product("H017", "Adalcrem ( Adaplene 15mg ) - A", "Tuýp", "Thuốc", 65000, 0.05, 13),
  product("H095", "Triluma Ấn 15g trị nám - O", "Tuýp", "", 500000, 0, 74),
  product("H00229", "Renewing Face Cream - 50ml", "Tuýp", "Mỹ Phẩm", 0, 0.08, 107),
];

export const CATALOG_SOURCE = "danhsach.xlsx";

export type OrderRecord = {
  id: string;
  patient_id: string;
  doctor_id: string;
  status: S["OrderStatus"];
  order_date: string;
  diagnosis: string;
  note: string;
  items: S["OrderItemOut"][];
  reviewed_by: string | null;
  reviewed_at: string | null;
  received_vnd: number;
  paid: boolean;
  created_at: string;
  version: number;
};

function line(
  no: number,
  code: string,
  quantity: number,
  usage: string,
  overrides: Partial<S["OrderItemOut"]> = {},
): S["OrderItemOut"] {
  const found = products.find((p) => p.code === code);
  if (!found) throw new Error(`unknown sample product ${code}`);
  return {
    line_no: no,
    product_code: found.code,
    name: found.name,
    source_type: found.source_type,
    unit: found.unit,
    catalog_route: found.route,
    route: found.route,
    route_reason: "",
    quantity,
    unit_price_vnd: found.price_vnd,
    usage,
    note: "",
    ...overrides,
  };
}

const TODAY = isoFromNow(0).slice(0, 10);

/** One draft (needs the doctor) and one approved order (both sheets), for two different patients. */
export const orders: OrderRecord[] = [
  {
    id: uuid(1, 41),
    patient_id: patientRef(1).id,
    doctor_id: DOCTOR_TAM,
    status: "draft",
    order_date: TODAY,
    diagnosis: "Nám · tăng sắc tố (mẫu)",
    note: "Tránh nắng, tái khám sau 2 tuần (mẫu).",
    items: [
      line(1, "H002", 3, "Uống 1 viên sau ăn tối, 7 ngày (mẫu)"),
      line(2, "H005", 1, "Bôi lớp mỏng sáng và tối (mẫu)"),
    ],
    reviewed_by: null,
    reviewed_at: null,
    received_vnd: 0,
    paid: false,
    created_at: isoFromNow(-3_600_000),
    version: 2,
  },
  {
    id: uuid(2, 41),
    patient_id: patientRef(2).id,
    doctor_id: DOCTOR_MAI,
    status: "approved",
    order_date: isoFromNow(-DAY).slice(0, 10),
    diagnosis: "Viêm da cơ địa nhẹ (mẫu)",
    note: "Dưỡng ẩm đều đặn (mẫu).",
    items: [
      line(1, "H014", 1, "Bôi ngày 2 lần vào vùng tổn thương, 10 ngày (mẫu)"),
      line(2, "H007", 1, "Rửa mặt sáng và tối (mẫu)"),
      line(3, "H015", 2, "", { route: "NONE", route_reason: "Đã cấp riêng (mẫu)" }),
    ],
    reviewed_by: DOCTOR_MAI,
    reviewed_at: isoFromNow(-DAY + 3_600_000),
    received_vnd: 0,
    paid: false,
    created_at: isoFromNow(-DAY),
    version: 3,
  },
];

export const DOCTOR_IDS = { tam: DOCTOR_TAM, an: DOCTOR_AN, mai: DOCTOR_MAI } as const;
