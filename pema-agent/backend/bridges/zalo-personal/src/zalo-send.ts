// ported from: src/zalo/send-reply-in-parts.ts (only `duongGuiZcaJs` and `laLoiMayChuTuChoi`)
// The splitting, retry-without-style and queueing of that file live in the Python API (the ported
// `send_reply_in_parts`); the bridge sends ONE part per call. No forced deviation except that the
// attachment helper below is new (the original sent file paths; the bridge receives bytes).
import { imageSize } from "image-size";
import type { Mention, SendMessageQuote, Style, ThreadType } from "zca-js";
import type { ZaloApi } from "./zalo-types.js";

/**
 * Một đoạn cần gửi (original `DoanCanGui`). `mentions` is the bridge's addition (the tag-member tool of
 * the original passed it to zca-js `sendMessage`); it follows the same rule as `styles`.
 */
export type DoanCanGui = {
  text: string;
  styles?: Style[];
  quote?: SendMessageQuote;
  mentions?: Mention[];
};

/**
 * Đường gửi cho kênh TÀI KHOẢN CÁ NHÂN (zca-js).
 *
 * Chỉ đính `styles` khi thật sự có - `sendMessage` của zca-js chỉ dựng
 * `textProperties` khi trường này khác rỗng, gửi mảng rỗng là thêm việc thừa.
 * Cùng lý do với `quote`: có trích dẫn thì zca-js đổi hẳn sang endpoint
 * `.../quote`, nên đính một giá trị rỗng là đổi đường gọi API mà không được gì.
 *
 * Gom vào một nhà máy thay vì để mỗi chỗ dựng `ReplyTarget` tự viết: ba chỗ tự
 * viết là ba cơ hội quên một trong hai luật trên, mà quên thì hỏng câm.
 */
export function duongGuiZcaJs(
  api: Pick<ZaloApi, "sendMessage">,
  threadId: string,
  threadType: ThreadType,
): (doan: DoanCanGui) => Promise<unknown> {
  return ({ text, styles, quote, mentions }) =>
    api.sendMessage(
      {
        msg: text,
        ...(styles && styles.length > 0 ? { styles } : {}),
        ...(quote ? { quote } : {}),
        ...(mentions && mentions.length > 0 ? { mentions } : {}),
      },
      threadId,
      threadType,
    );
}

/**
 * Máy chủ Zalo có TRẢ LỜI và từ chối, hay là lỗi đường truyền không rõ kết cục?
 *
 * Phân biệt được điều này mới dám gửi lại: máy chủ đã từ chối nghĩa là KHÔNG có
 * tin nào lọt qua, gửi lại là an toàn. Còn timeout hay đứt mạng thì tin có thể
 * đã tới nơi - gửi lại là nhân đôi tin trước mặt người dùng.
 *
 * Dấu hiệu: zca-js gắn `code` dạng số cho lỗi do máy chủ trả về
 * (`ZaloApiError`), lỗi mạng thì không có.
 *
 * (Verified in zca-js 2.1.2: `ZaloApiError` stores `code || null`, so a server code of 0 reads as no
 * code, i.e. transport. Every real rejection code is non-zero.)
 */
export function laLoiMayChuTuChoi(err: unknown): boolean {
  return typeof (err as { code?: unknown } | null)?.code === "number";
}

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp", "bmp"]);

export type AttachmentSourceBuffer = {
  data: Buffer;
  filename: `${string}.${string}`;
  metadata: { totalSize: number; width?: number; height?: number };
};

/**
 * Build a zca-js in-memory attachment. For images zca-js reads `width/height` from `metadata` when the
 * source is a buffer (it only calls `imageMetadataGetter` for file paths), so they are measured here with
 * `image-size`, the same library as the original getter. The bridge never writes the bytes to disk.
 */
export function buildAttachmentSource(
  filename: `${string}.${string}`,
  data: Buffer,
): AttachmentSourceBuffer {
  const extension = filename.slice(filename.lastIndexOf(".") + 1).toLowerCase();
  const metadata: AttachmentSourceBuffer["metadata"] = { totalSize: data.byteLength };
  if (!IMAGE_EXTENSIONS.has(extension)) return { data, filename, metadata };
  try {
    const { width, height } = imageSize(data);
    return width && height
      ? { data, filename, metadata: { ...metadata, width, height } }
      : { data, filename, metadata };
  } catch {
    return { data, filename, metadata };
  }
}
