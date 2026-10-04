// ported from: web/src/pages/mo-ta-loai-kenh.test.ts
//
// Deviations: `TOOL_KHONG_CHAY_TREN_BOT` was imported from `src/zalo-bot/nang-luc-kenh-bot.ts`; the
// table is now BE data (`ChannelCapabilities.blocked_tools` of the zalo_bot channel), so this file
// keeps a mirror of its eight keys. Change the BE table and this mirror together, or the test below
// says so. One extra case covers the new `zalo_oa` sentence.

import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  MO_TA_KENH,
  MO_TA_KENH_BOT,
  MO_TA_KENH_CA_NHAN,
  MO_TA_KENH_OA,
} from "@/lib/admin/accounts/mo-ta-loai-kenh";

/** Bản sao tám key của bảng chặn kênh bot (key -> lý do ngắn, chỉ để người đọc test hiểu). */
const TOOL_KHONG_CHAY_TREN_BOT: Record<string, { hint: string }> = {
  send_file: { hint: "Zalo Bot API không có method gửi file" },
  create_word_document: { hint: "Tạo được file nhưng không gửi được tài liệu" },
  create_excel_file: { hint: "Tạo được file nhưng không gửi được tài liệu" },
  create_image: { hint: "Zalo Bot API chỉ gửi ảnh qua URL công khai" },
  tai_video: { hint: "Zalo Bot API không có method gửi video" },
  add_reaction: { hint: "Zalo Bot API không có method thả cảm xúc" },
  tag_member: { hint: "Zalo Bot API không có method tag thành viên trong nhóm" },
  get_group_info: { hint: "Zalo Bot API không đọc được danh sách thành viên nhóm" },
};

/**
 * Canh câu mô tả loại kênh trên trang Accounts.
 *
 * Cùng khuôn với ca canh `LUAT_PERSONA_KENH_BOT` ở
 * `src/zalo-bot/lich-hen-tren-kenh-bot.test.ts`, và ra đời vì đúng lỗ mà ca đó
 * KHÔNG phủ: persona được canh, còn chuỗi dashboard thì không - nên khi lịch
 * hẹn nối xong ở V3.19, câu "không đặt lịch hẹn" nằm lại trên giao diện.
 *
 * Vì sao đáng một file test riêng: khối này chỉ hiện lúc TẠO account, ngay
 * trên dòng "Chốt lúc tạo, không đổi được sau đó". Nói sai ở đây đẩy người cần
 * lịch hẹn sang kênh CÁ NHÂN - kênh CÓ rủi ro bị Zalo khóa nick - và sửa lại
 * đòi xóa account, mà xóa account thì dọn luôn toàn bộ lịch hẹn của nó.
 */
describe("mô tả loại kênh trên trang Accounts", () => {
  it("mô tả kênh bot KHÔNG nói bot không đặt được lịch hẹn", () => {
    assert.doesNotMatch(MO_TA_KENH_BOT, /lịch|hẹn|schedule/i);
  });

  it("mô tả kênh bot nêu ĐỦ CẢ TÁM tool bị chặn, không sót cái nào", () => {
    // Bỏ chữ "lịch hẹn" mà bỏ luôn phần đúng thì thành nói THIẾU theo chiều
    // ngược lại - người vận hành chọn kênh bot rồi mới phát hiện không gửi
    // được file. Vòng rà soát 2 bắt được đúng ca đó: bản đầu sót
    // `get_group_info`, mà ca test thì tự nhận là "nêu ĐÚNG những gì Bot API
    // không làm được" trong khi chỉ đo 4 trong 7.
    //
    // Đối chiếu thẳng với BẢNG CHẶN thay vì gõ tay danh sách: gõ tay là danh
    // sách này và bảng kia trôi khỏi nhau ngay lần thêm/bớt tool tiếp theo.
    const chuCanCo: Record<string, RegExp> = {
      send_file: /gửi được file/i,
      // `/Word/i` trần trụi khớp cả "passWORD" - neo vào cụm có nghĩa
      create_word_document: /tài liệu Word/i,
      create_excel_file: /Excel/i,
      create_image: /ảnh tự vẽ/i,
      tai_video: /video tải về/i,
      add_reaction: /thả cảm xúc/i,
      tag_member: /tag thành viên/i,
      get_group_info: /thành viên nhóm/i,
    };

    assert.deepEqual(
      Object.keys(chuCanCo).sort(),
      Object.keys(TOOL_KHONG_CHAY_TREN_BOT).sort(),
      "bảng chặn đã đổi mà câu mô tả trên dashboard chưa theo - người vận hành đọc phải thông tin cũ",
    );

    // Mỗi key phải khớp một ĐOẠN CHỮ RIÊNG. Hai bản trước đều hụt:
    //  - bản 1 cho ba key cùng ánh xạ `/file/i`, tức bảy khẳng định chỉ là năm.
    //  - bản 2 khẳng định các `RegExp.source` KHÁC nhau - và vẫn thủng: một
    //    tool mới ánh xạ `/file/i` có `source` khác `/gửi được file/i` nên qua
    //    được cửa, trong khi vẫn khớp đúng đoạn chữ của `send_file`. Đo được:
    //    phép phá đó XANH trên bản 2.
    //
    // Đo đúng bản chất là so VỊ TRÍ KHỚP: hai key khớp chồng lấn nhau nghĩa là
    // key sau đi ké khẳng định của key trước, bất kể mẫu viết thế nào.
    const doanKhop: { key: string; dau: number; cuoi: number }[] = [];
    for (const [key, m] of Object.entries(chuCanCo)) {
      // Cờ `g` làm `.index` thành `undefined` - không có nó thì assert dưới
      // bắn với thông điệp "không nhắc tới", tức chỉ SAI nguyên nhân và người
      // debug đi tìm nhầm chỗ. Mẫu khớp RỖNG thì rời nhau với mọi span khác
      // nên qua cửa chồng lấn dù chuỗi không hề nhắc tới tool đó.
      assert.ok(!m.global, `mẫu của "${key}" có cờ g - phép đo span không đọc được vị trí`);
      const kq = MO_TA_KENH_BOT.match(m);
      assert.ok(kq && kq.index !== undefined, `mô tả không nhắc tới giới hạn của "${key}"`);
      assert.ok(
        kq[0].length > 0,
        `mẫu của "${key}" khớp chuỗi RỖNG - khẳng định rỗng, không đo gì`,
      );
      doanKhop.push({ key, dau: kq.index, cuoi: kq.index + kq[0].length });
    }

    for (const a of doanKhop) {
      for (const b of doanKhop) {
        if (a.key >= b.key) continue;
        assert.ok(
          a.cuoi <= b.dau || b.cuoi <= a.dau,
          `"${a.key}" và "${b.key}" khớp CHỒNG LẤN cùng một đoạn chữ - key sau đi ké key trước, phép đo mất răng`,
        );
      }
    }

    assert.match(MO_TA_KENH_BOT, /Zalo Bot API/, "không nói rõ đây là giới hạn của nền tảng");
    assert.match(
      MO_TA_KENH_BOT,
      /không có rủi ro bị khóa/i,
      "không nêu cái ĐƯỢC, người đọc chỉ thấy cái mất",
    );
  });

  it("mô tả kênh cá nhân vẫn cảnh báo rủi ro khóa nick", () => {
    // Đây là cảnh báo an toàn, không phải chữ trang trí: repo chốt "chỉ dùng
    // nick phụ" vì zca-js là giao thức không chính thức.
    assert.match(MO_TA_KENH_CA_NHAN, /rủi ro/i);
    assert.match(MO_TA_KENH_CA_NHAN, /nick phụ/i);
  });

  it("mô tả kênh Zalo OA nói rõ là chưa hỗ trợ", () => {
    assert.match(MO_TA_KENH_OA, /chưa hỗ trợ/i);
  });

  it("mỗi loại kênh của contract có đúng một câu mô tả", () => {
    assert.deepEqual(Object.keys(MO_TA_KENH).sort(), ["zalo_bot", "zalo_oa", "zalo_personal"]);
    assert.equal(MO_TA_KENH.zalo_bot, MO_TA_KENH_BOT);
    assert.equal(MO_TA_KENH.zalo_personal, MO_TA_KENH_CA_NHAN);
  });
});
