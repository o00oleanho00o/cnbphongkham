// ported from: web/src/pages/mo-ta-loai-kenh.ts
//
// Deviations: the original `loai` ("ca_nhan" | "bot") is the contract enum `channel`
// (`zalo_personal` | `zalo_bot` | `zalo_oa`), so the two sentences are indexed by `ChannelKind`.
// `zalo_oa` has no original: it is not supported in this phase (PLAN-AI01 section 8), and the sentence
// says so. `NHAN_KENH` / `NHAN_KENH_NGAN` are new (labels shared by the accounts page and the channel
// switchboard). The test no longer imports the bot block table from `src/` (the platform is Python
// now: `ChannelCapabilities.blocked_tools`), it keeps a mirror of the eight keys, see the test file.
import type { Schemas } from "@/lib/api";

type ChannelKind = Schemas["ChannelKind"];

/**
 * Câu mô tả các loại kênh, hiện ngay dưới ô chọn "Loại kênh" lúc TẠO account.
 *
 * Tách khỏi JSX để test đọc được. Không phải cầu kỳ: `channel` chốt lúc tạo và
 * không đổi được sau đó, nên câu này là thứ người vận hành dựa vào để ra một
 * quyết định KHÔNG ĐẢO NGƯỢC ĐƯỢC (sửa lại đòi xóa account, mà xóa account thì
 * dọn luôn toàn bộ lịch hẹn của nó).
 *
 * Đã trả giá một lần: câu cho kênh bot từng ghi "không đặt lịch hẹn" và nằm lại
 * sau khi lịch hẹn đã nối xong ở V3.19 - tức nó đẩy người cần lịch hẹn sang
 * kênh cá nhân, kênh CÓ rủi ro bị Zalo khóa nick. Luật persona của kênh bot có
 * test canh đúng chuyện này (`lich-hen-tren-kenh-bot.test.ts`), còn chuỗi
 * dashboard thì không - nên nó là chỗ duy nhất trôi lại. Giờ có canh.
 *
 * RÀNG BUỘC KÈM THEO: ca test của file này đối chiếu câu mô tả kênh bot với
 * bảng tool bị chặn trên kênh bot, để hai bên không trôi khỏi nhau. Ở bản gốc
 * đó là import DUY NHẤT xuyên ranh giới `web/` -> `src/`, chỉ hợp lệ cho file
 * `.test.ts` (mã app import là kéo mã server vào bundle trình duyệt). Ở đây bảng
 * là dữ liệu của BE (`ChannelCapabilities.blocked_tools`), nên test giữ một bản
 * sao tám key: khi BE đổi bảng chặn thì bản sao và câu mô tả phải đổi cùng nhau.
 *
 * Bài học cũ vẫn đúng: khối này từng viết SAI cơ chế HAI LẦN (chuyện `process`
 * trong mã web và `@types/node`), mỗi lần đều nghe hợp lý và chỉ lộ ra khi có
 * người đo. Mã app không được dùng `process` / `Buffer` / `__dirname`; riêng
 * `process.env.NEXT_PUBLIC_*` là biến build của Next, được phép.
 */

export const MO_TA_KENH_BOT =
  "Không gửi được file, tài liệu Word/Excel, ảnh tự vẽ, video tải về, thả cảm xúc, tag thành viên, " +
  "và không đọc được danh sách thành viên nhóm - đó là giới hạn của Zalo Bot API. " +
  "Đổi lại không có rủi ro bị khóa tài khoản.";

export const MO_TA_KENH_CA_NHAN =
  "Dùng nick Zalo thật qua giao thức không chính thức - đủ tính năng nhất nhưng CÓ rủi ro " +
  "bị Zalo khóa. Chỉ dùng nick phụ.";

export const MO_TA_KENH_OA =
  "Zalo OA (Official Account) và ZNS: chưa hỗ trợ ở giai đoạn này - phòng khám chưa có OA/ZNS " +
  "nên chưa tạo được loại kênh này.";

/** Câu mô tả theo loại kênh của contract (`AccountOut.channel`). */
export const MO_TA_KENH: Record<ChannelKind, string> = {
  zalo_bot: MO_TA_KENH_BOT,
  zalo_personal: MO_TA_KENH_CA_NHAN,
  zalo_oa: MO_TA_KENH_OA,
};

/** Tên đầy đủ của kênh, dùng ở thẻ account và bảng điều khiển kênh. */
export const NHAN_KENH: Record<ChannelKind, string> = {
  zalo_bot: "Tài khoản bot chính thức",
  zalo_personal: "Tài khoản cá nhân",
  zalo_oa: "Zalo OA",
};

/** Tên ngắn của kênh cho badge. */
export const NHAN_KENH_NGAN: Record<ChannelKind, string> = {
  zalo_bot: "Bot chính thức",
  zalo_personal: "Nick cá nhân",
  zalo_oa: "Zalo OA",
};
