// ported from: web/src/pages/kb-source-row.tsx
"use client";

// Deviations: DTO is the contract's `KbSource` (English fields); `soAgent` is no longer in the list
// response, so the page counts agents per source and passes `agentCount` (null = unknown, shown as "-");
// new column "Bác sĩ duyệt" (doctor sign-off, `approved_by_clinical_owner`).
type KbSourceListItem = Schemas["KbSource"];

import { useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { Badge, ToggleKnob, formatTime, O_GHIM_PHAI } from "@/components/admin/shared/ui-bits";
import {
  IconEye,
  IconUndo,
  IconUsers,
  IconWarning,
} from "@/components/admin/shared/dashboard-icons";

/** "1,2 KB" / "3,4 MB" từ số byte - 0 byte (nguồn gõ tay) hiện "-" */
function formatBytes(soByte: number): string {
  if (soByte <= 0) return "-";
  if (soByte < 1024) return `${soByte} B`;
  if (soByte < 1024 * 1024)
    return `${(soByte / 1024).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} KB`;
  return `${(soByte / (1024 * 1024)).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} MB`;
}

const NHAN_TRANG_THAI: Record<
  KbSourceListItem["status"],
  { tone: "blue" | "gray" | "green" | "red" | "amber"; text: string }
> = {
  cho_xu_ly: { tone: "gray", text: "Chờ xử lý" },
  dang_xu_ly: { tone: "amber", text: "Đang xử lý" },
  san_sang: { tone: "green", text: "Sẵn sàng" },
  hong: { tone: "red", text: "Hỏng" },
};

export function KbSourceRow({
  source,
  agentCount,
  canApprove,
  onToggleApproval,
  onReindex,
  onDelete,
  onViewChunks,
  onAssignAgents,
  guideTopic,
  onEditGuide,
}: {
  source: KbSourceListItem;
  /** Số agent đọc được nguồn này; null = chưa biết (không có quyền xem agent hoặc đang tải) */
  agentCount: number | null;
  /** `kb.manage`: chỉ người có quyền mới đổi được chữ ký duyệt của bác sĩ */
  canApprove: boolean;
  onToggleApproval: () => Promise<void>;
  onReindex: () => Promise<void>;
  onDelete: () => void;
  /** I21: mở modal xem đoạn đã cắt - cách duy nhất người vận hành tự phát hiện lỗi đọc file */
  onViewChunks: () => void;
  /** Mở modal gán nguồn này cho agent - đường thoát khỏi ngõ cụt "nạp xong mà bot không thấy" */
  onAssignAgents: () => void;
  /** Package U7: topic of the staff-guide article this source is ("" = no topic); null = not an article */
  guideTopic: string | null;
  /** `kb.manage`: mở modal đưa nguồn vào / gỡ khỏi mục Hướng dẫn; undefined = không có quyền */
  onEditGuide?: () => void;
}) {
  const [dangXuLyLai, setDangXuLyLai] = useState(false);
  const [loiXuLyLai, setLoiXuLyLai] = useState("");
  const trangThai = NHAN_TRANG_THAI[source.status];
  const daDuyet = source.approved_by_clinical_owner ?? false;
  const [dangDuyet, setDangDuyet] = useState(false);

  async function doiDuyet() {
    setDangDuyet(true);
    setLoiXuLyLai("");
    try {
      await onToggleApproval();
    } catch (err) {
      setLoiXuLyLai(errorMessage(err));
    } finally {
      setDangDuyet(false);
    }
  }

  async function xuLyLai() {
    setDangXuLyLai(true);
    setLoiXuLyLai("");
    try {
      await onReindex();
    } catch (err) {
      setLoiXuLyLai(errorMessage(err));
    } finally {
      setDangXuLyLai(false);
    }
  }

  return (
    <tr className="border-b border-line/60 last:border-0 hover:bg-tile/40">
      <td className="max-w-xs px-4 py-3 text-ink">
        <div className="truncate font-medium">{source.name}</div>
        {source.status === "hong" && source.error && (
          <div className="mt-0.5 truncate text-label text-danger" title={source.error}>
            {source.error}
          </div>
        )}
        {/* Số lần đã thử cũng có nghĩa với nguồn đang KẸT ở "Chờ xử lý" (đã tiêu
            hết lượt thử nên không nguồn nào giành nữa) - không riêng gì nguồn Hỏng */}
        {(source.status === "hong" ||
          (source.status === "cho_xu_ly" && (source.attempts ?? 0) > 0)) && (
          <div className="mt-0.5 text-micro text-ink-soft">Đã thử {source.attempts ?? 0} lần</div>
        )}
        {guideTopic !== null && (
          <div className="mt-1">
            <Badge tone="blue" dot={false}>
              {guideTopic === "" ? "Hướng dẫn" : `Hướng dẫn · ${guideTopic}`}
            </Badge>
          </div>
        )}
        {loiXuLyLai && <div className="mt-0.5 text-label text-danger">{loiXuLyLai}</div>}
      </td>
      {/* "Loại" và "Định dạng" GỘP làm một: nguồn `file` luôn có định dạng, nguồn
          `text` luôn không - hai cột rời nhau chỉ tốn bề ngang mà không nói thêm
          gì. Bề ngang đó có giá thật: bảng rộng quá khung là cột thao tác
          ("Xem đoạn", "Xóa") bị đẩy ra ngoài, phải cuộn ngang mới thấy - đúng
          lý do người dùng báo "không thấy chỗ xem nội dung đã nạp". */}
      <td className="px-4 py-3 text-ink-soft">
        {source.kind === "file" ? source.format || "file" : "Gõ tay"}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <Badge tone={trangThai.tone}>{trangThai.text}</Badge>
      </td>
      {/* Cột này là thứ DUY NHẤT phân biệt "đã cắt đoạn xong" với "bot dùng
          được": `kb_search` chỉ vào toolset của agent khi agent đó có ít nhất
          một nguồn. Nguồn 0 agent mà chỉ hiện "Sẵn sàng" là mọi tín hiệu trên
          màn hình đều nói xong rồi trong khi bot không hề thấy tài liệu. */}
      <td className="px-4 py-3">
        <button
          onClick={onAssignAgents}
          title={
            agentCount === 0
              ? "Chưa agent nào đọc được - bấm để gán"
              : "Đổi agent đọc được nguồn này"
          }
          className={`flex cursor-pointer items-center gap-1.5 text-small hover:underline ${
            agentCount === 0 ? "text-warning" : "text-ink-soft hover:text-ink"
          }`}
        >
          {agentCount === null ? (
            "-"
          ) : agentCount === 0 ? (
            <>
              <IconWarning size={14} />
              Chưa gán
            </>
          ) : (
            <>
              <IconUsers size={14} />
              {agentCount} agent
            </>
          )}
        </button>
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        {canApprove ? (
          <button
            onClick={() => void doiDuyet()}
            disabled={dangDuyet}
            aria-pressed={daDuyet}
            title={
              daDuyet
                ? "Bỏ chữ ký duyệt của bác sĩ"
                : "Bác sĩ xác nhận nguồn này đúng để trợ lý trả lời bệnh nhân"
            }
            className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ToggleKnob on={daDuyet} />
          </button>
        ) : null}
        <div
          className={`mt-1 text-label font-medium ${daDuyet ? "text-success" : "text-warning"}`}
          title={
            daDuyet
              ? "Bác sĩ đã duyệt nguồn này"
              : "Chưa được bác sĩ duyệt: kênh bệnh nhân không dùng nguồn này"
          }
        >
          {daDuyet ? "Đã duyệt" : "Chưa duyệt"}
        </div>
      </td>
      <td className="px-4 py-3 text-ink-soft">{source.chunk_count ?? 0}</td>
      <td className="px-4 py-3 text-ink-soft">{formatBytes(source.byte_size ?? 0)}</td>
      <td className="px-4 py-3 text-ink-soft">{formatTime(source.created_at)}</td>
      <td className={`px-4 py-3 ${O_GHIM_PHAI}`}>
        <div className="flex items-center justify-end gap-3 whitespace-nowrap">
          {/* Hiện cho CẢ "cho_xu_ly" lẫn "hong": nguồn có thể KẸT ở "Chờ xử lý"
              mà không có đường thoát nào - xảy ra khi hạ "Số lần thử lại một
              nguồn" trên trang Cấu hình lúc đang chạy, nguồn đã tiêu quá số lượt
              mới thì `giaNguonChoXuLy` không giành nữa và nó nằm đó vĩnh viễn.
              Route /reindex cấp lại lượt thử (soLanThu = 0) nên bấm là thoát;
              nó chỉ từ chối 409 với "dang_xu_ly", không phải trạng thái này. */}
          {(source.status === "hong" || source.status === "cho_xu_ly") && (
            <button
              onClick={() => void xuLyLai()}
              disabled={dangXuLyLai}
              title="Xử lý lại"
              className="flex cursor-pointer items-center gap-1 text-small text-brand-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-brand-400"
            >
              <IconUndo size={14} />
              {dangXuLyLai ? "Đang xử lý..." : "Xử lý lại"}
            </button>
          )}
          {onEditGuide && (
            <button
              onClick={onEditGuide}
              title="Hiện nguồn này trong mục Hướng dẫn của nhân viên"
              className="cursor-pointer text-small text-ink-soft hover:text-ink hover:underline"
            >
              Nhãn hướng dẫn
            </button>
          )}
          <button
            onClick={onViewChunks}
            title="Xem đoạn đã cắt"
            className="flex cursor-pointer items-center gap-1 text-small text-ink-soft hover:text-ink hover:underline"
          >
            <IconEye size={14} />
            Xem đoạn
          </button>
          <button
            onClick={onDelete}
            className="cursor-pointer text-small text-danger hover:underline"
          >
            Xóa
          </button>
        </div>
      </td>
    </tr>
  );
}
