// ported from: web/src/dashboard-api-client.ts (types TuningDef, TuningGroup, TuningValue)
//
// Deviation: the original server sent `defs` (a record by key) and `values` (a list). The contract sends one
// `TuningOut {groups, items[]}` where each item carries its definition AND its current value. The pages and
// the field components were written against the original shapes, so `tuningTuApi` rebuilds exactly those
// shapes from the items and the ported components stay untouched. `fromEnv` is the original's "no override
// row": it is `!overridden`. `enum` is the contract's `select`; the timezone list is still built in the
// browser (the BE does not send 418 zone names), keyed on `BOT_TIMEZONE`.
import type { Schemas } from "@/lib/api";
import { MOC_CUA_SO_NGU_CANH, type MocSoGoiY } from "@/lib/admin/tuning/tuning-number-presets";

type TuningItem = Schemas["TuningItem"];

export type TuningGroup = Schemas["TuningGroup"];

export type TuningValue = {
  key: string;
  value: number | boolean | string;
  /** Giá trị khi KHÔNG có dòng đè - dùng để biết lúc nào nên xóa dòng đè thay vì ghi trùng */
  macDinh: number | boolean | string;
  fromEnv: boolean;
};

/** Một tham số chỉnh được, mô tả lấy thẳng từ backend nên web không chép lại danh mục */
export type TuningDef = {
  group: string;
  label: string;
  hint: string;
} & (
  | {
      kind: "number";
      min: number;
      max: number;
      unit?: string;
      presets?: { value: number; label: string; hint: string }[];
      hienQuyDoiToken?: boolean;
    }
  | { kind: "boolean" }
  | { kind: "enum"; options: string[] }
  | { kind: "timezone" }
);

/** Key of the timezone parameter: its dropdown is built in the browser from the platform's zone list */
export const KHOA_MUI_GIO = "BOT_TIMEZONE";

/** Context window presets keep the model hints of the shared list; other keys only get the plain numbers */
const PRESETS_CO_NHAN: Record<string, readonly MocSoGoiY[]> = {
  LLM_CONTEXT_WINDOW: MOC_CUA_SO_NGU_CANH,
};

function presetsOf(item: TuningItem): { value: number; label: string; hint: string }[] | undefined {
  const known = PRESETS_CO_NHAN[item.key];
  if (known) return known.map((m) => ({ ...m }));
  return item.presets?.map((value) => ({ value, label: value.toLocaleString("vi-VN"), hint: "" }));
}

function defOf(item: TuningItem): TuningDef {
  const base = { group: item.group, label: item.label, hint: item.hint };
  if (item.key === KHOA_MUI_GIO) return { ...base, kind: "timezone" };
  if (item.kind === "boolean") return { ...base, kind: "boolean" };
  if (item.kind === "select") return { ...base, kind: "enum", options: item.options ?? [] };
  return {
    ...base,
    kind: "number",
    min: item.min ?? Number.NEGATIVE_INFINITY,
    max: item.max ?? Number.POSITIVE_INFINITY,
    presets: presetsOf(item),
    hienQuyDoiToken: item.token_estimate_hint ?? false,
  };
}

function valueOf(item: TuningItem): TuningValue {
  return {
    key: item.key,
    value: item.value,
    macDinh: item.default,
    fromEnv: !(item.overridden ?? false),
  };
}

/** `TuningOut` -> the three structures the tuning page works with */
export function tuningTuApi(out: Schemas["TuningOut"]): {
  groups: TuningGroup[];
  defs: Record<string, TuningDef>;
  values: Record<string, TuningValue>;
} {
  return {
    groups: out.groups,
    defs: Object.fromEntries(out.items.map((item) => [item.key, defOf(item)])),
    values: Object.fromEntries(out.items.map((item) => [item.key, valueOf(item)])),
  };
}
