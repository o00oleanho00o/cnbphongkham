// ported from: src/config/tuning-number-presets.test.ts
//
// Deviation: the original also checked every preset against `TUNING_DEFS` (min/max, defaults) and the token
// estimate helper, which live on the Python side now (`tests/config`). Kept here: the invariants of the
// lists themselves and the manual-entry rule, which are what the dropdown relies on.
import assert from "node:assert/strict";
import { describe, it } from "vitest";

import {
  dangNhapTayCuaSo,
  laMocCoSan,
  MOC_CUA_SO_NGU_CANH,
  MOC_TRAN_TOKEN_VIET_RA,
  TRAN_KY_TU_HINT,
  type MocSoGoiY,
} from "@/lib/admin/tuning/tuning-number-presets";

const DANH_SACH: { ten: string; moc: readonly MocSoGoiY[] }[] = [
  { ten: "cửa sổ ngữ cảnh", moc: MOC_CUA_SO_NGU_CANH },
  { ten: "trần token viết ra", moc: MOC_TRAN_TOKEN_VIET_RA },
];

for (const { ten, moc } of DANH_SACH) {
  describe(`mốc ${ten}`, () => {
    it("`label` là ĐÚNG con số, không kèm chữ nào khác", () => {
      for (const m of moc) {
        assert.equal(m.label, m.value.toLocaleString("vi-VN"));
      }
    });

    it("mọi mốc đều có `hint` - số trần trụi thì không ai chọn nổi", () => {
      for (const m of moc) {
        assert.ok(m.hint.trim() !== "", `mốc ${m.value} thiếu hint`);
      }
    });

    it("hint không vượt trần ký tự - dài hơn là popup chạm mép cửa sổ rồi bị cắt", () => {
      for (const m of moc) {
        assert.ok(
          m.hint.length <= TRAN_KY_TU_HINT,
          `hint của mốc ${m.value} dài ${m.hint.length} ký tự, trần là ${TRAN_KY_TU_HINT}`,
        );
      }
    });

    it("không có mốc trùng giá trị - menu hiện hai dòng chọn ra cùng một số", () => {
      assert.equal(new Set(moc.map((m) => m.value)).size, moc.length);
    });

    it("mốc sắp tăng dần - menu nhảy số lung tung thì khó chọn", () => {
      const so = moc.map((m) => m.value);
      assert.deepEqual(
        so,
        [...so].sort((a, b) => a - b),
      );
    });
  });
}

describe("dangNhapTayCuaSo", () => {
  it("đã bấm Tùy chỉnh thì luôn là nhập tay, dù giá trị đang trùng một mốc", () => {
    assert.equal(dangNhapTayCuaSo(MOC_CUA_SO_NGU_CANH, "128000", true), true);
  });

  it("chuỗi rỗng không phải nhập tay - nghĩa là theo Cấu hình chung", () => {
    assert.equal(dangNhapTayCuaSo(MOC_CUA_SO_NGU_CANH, "  ", false), false);
  });

  it("giá trị trùng một mốc thì chỉ cần menu", () => {
    assert.equal(dangNhapTayCuaSo(MOC_CUA_SO_NGU_CANH, "128000", false), false);
  });

  it("giá trị không thuộc mốc nào thì hiện ô nhập tay", () => {
    assert.equal(dangNhapTayCuaSo(MOC_CUA_SO_NGU_CANH, "150000", false), true);
  });

  it("chuỗi rác lộ ra ở ô nhập để còn sửa", () => {
    assert.equal(dangNhapTayCuaSo(MOC_CUA_SO_NGU_CANH, "abc", false), true);
  });

  it("laMocCoSan nhận đúng giá trị của danh sách", () => {
    assert.equal(laMocCoSan(MOC_CUA_SO_NGU_CANH, 128_000), true);
    assert.equal(laMocCoSan(MOC_CUA_SO_NGU_CANH, 1), false);
  });
});
