// ported from: web/src/pages/kb-add-source-modal.tsx
"use client";

// Deviations: typed client; the upload is multipart through a `bodySerializer` (the generated body type
// calls the file a string); the size cap is read from `GET /admin/model/tuning` (needs `admin.model`:
// without it the cap stays unknown and only the server enforces it, as the original already allowed).

import { useEffect, useState } from "react";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { FileDropZone } from "@/components/admin/shared/file-drop-zone";
import { DINH_DANG_HO_TRO } from "@/lib/admin/shared/kb-formats";
import { tenNguonTuTenFile } from "@/lib/admin/kb/kb-source-name-from-file";
import {
  layNhanTranDungLuong,
  layThongDiepVuotTran,
  layTranDungLuongMB,
  vuotTranDungLuong,
} from "@/lib/admin/kb/kb-upload-size-guard";

type Tab = "file" | "text";

/**
 * Modal thêm nguồn: hai tab "Tải file lên" (multipart, trả 202 - xử lý ở nền)
 * và "Gõ nội dung" (JSON, trả 201 - vẫn `cho_xu_ly` chờ worker cắt đoạn).
 * Đóng modal ngay sau khi tạo THÀNH CÔNG lệnh tạo, không đợi worker xử lý xong -
 * bảng nguồn ở trang cha tự cập nhật trạng thái khi poll lại.
 */
export function KbAddSourceModal({
  onClose,
  onCreated,
  fileBanDau,
}: {
  onClose: () => void;
  onCreated: () => void;
  /** File thả thẳng vào bảng ở trang cha - modal mở ra đã chọn sẵn file này */
  fileBanDau?: File;
}) {
  const [tab, setTab] = useState<Tab>("file");
  const [ten, setTen] = useState(fileBanDau ? tenNguonTuTenFile(fileBanDau.name) : "");
  const [file, setFile] = useState<File | null>(fileBanDau ?? null);
  const [noiDung, setNoiDung] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tranMB, setTranMB] = useState<number | null>(null);
  const nen = useChotNen(onClose);

  // I20: đọc trần dung lượng THẬT từ cấu hình (không hard-code) để hiện ngay
  // trên modal và chặn SỚM ở client - server vẫn là chốt cuối cùng nếu tải
  // chưa xong kịp lúc người dùng chọn file (tranMB còn null thì không chặn).
  useEffect(() => {
    let huy = false;
    unwrap(http.GET("/api/v1/admin/model/tuning"))
      .then((d) => !huy && setTranMB(layTranDungLuongMB(d.items)))
      .catch(() => undefined);
    return () => {
      huy = true;
    };
  }, []);

  const hopLe =
    tab === "file" ? Boolean(ten.trim() && file) : Boolean(ten.trim() && noiDung.trim());

  function chonFile(f: File | null) {
    setError("");
    if (f && tranMB !== null && vuotTranDungLuong(f.size, tranMB)) {
      setError(layThongDiepVuotTran(f.name, tranMB));
      setFile(null);
      return;
    }
    setFile(f);
    // Điền sẵn tên nguồn từ tên file khi ô tên còn trống - bỏ một bước gõ tay
    // cho ca thường gặp nhất. Người dùng sửa lại được, và đã gõ gì rồi thì
    // KHÔNG đè lên.
    if (f) setTen((truoc) => (truoc.trim() ? truoc : tenNguonTuTenFile(f.name)));
  }

  // Trần dung lượng tải về BẤT ĐỒNG BỘ, nên có khung hở: file được chọn (bấm,
  // thả, hoặc thả từ trang cha) TRƯỚC khi `tranMB` về thì không nhánh nào kiểm
  // nó. Kiểm lại đúng một lần khi trần vừa tới, để người dùng biết ngay thay vì
  // bấm Lưu rồi mới ăn lỗi từ server.
  useEffect(() => {
    if (tranMB === null || !file) return;
    if (vuotTranDungLuong(file.size, tranMB)) {
      setError(layThongDiepVuotTran(file.name, tranMB));
      setFile(null);
    }
  }, [tranMB, file]);

  async function luu() {
    if (!hopLe) return;
    setBusy(true);
    setError("");
    try {
      if (tab === "file") {
        if (!file) return;
        await unwrap(
          http.POST("/api/v1/admin/kb/sources/file", {
            body: { file: file.name, name: ten.trim() },
            // multipart: the browser sets the boundary, never set content-type by hand
            bodySerializer: () => {
              const form = new FormData();
              form.append("file", file);
              form.append("name", ten.trim());
              return form;
            },
          }),
        );
      } else {
        await unwrap(
          http.POST("/api/v1/admin/kb/sources/text", { body: { name: ten.trim(), text: noiDung } }),
        );
      }
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    /* `max-h-[85dvh]` + thân cuộn riêng: modal này cao 490px (ô tên + vùng thả
       file, hoặc textarea `resize-y` người dùng kéo cao được tùy ý). Không có
       trần thì ở cửa sổ thấp nó tràn khỏi màn theo CẢ HAI đầu mà không cuộn
       được - đo ở 844x390: tiêu đề mất 50px trên, nút "Thêm nguồn" nằm ở 424
       tức là ngoài màn, cuộn kiểu gì cũng không tới. `dvh` chứ không `vh` để
       trên điện thoại còn trừ đúng phần thanh địa chỉ đang chiếm chỗ. */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]"
      {...nen}
    >
      <div className="flex max-h-[85dvh] w-full max-w-lg flex-col rounded-card bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="font-semibold text-ink">Thêm nguồn</div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        {/* Segmented control 2 tab - tự dựng, không phải <select> hay tab mặc định trình duyệt */}
        <div className="flex gap-1 border-b border-line px-5 pt-3">
          {(
            [
              ["file", "Tải file lên"],
              ["text", "Gõ nội dung"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`cursor-pointer rounded-t-lg px-3 py-2 text-small font-medium transition-colors ${
                tab === key
                  ? "border-b-2 border-brand-500 text-brand-600"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label htmlFor="kb-ten" className="mb-1.5 block text-small font-medium text-ink">
              Tên nguồn
            </label>
            <input
              id="kb-ten"
              className="gc-input w-full"
              value={ten}
              onChange={(e) => setTen(e.target.value)}
              placeholder="vd: Chính sách đổi trả"
              maxLength={200}
            />
          </div>

          {tab === "file" ? (
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-small font-medium text-ink">File</span>
                {tranMB !== null && (
                  <span className="text-label text-ink-soft">{layNhanTranDungLuong(tranMB)}</span>
                )}
              </div>
              <FileDropZone
                onFile={(f) => chonFile(f)}
                accept={DINH_DANG_HO_TRO.map((d) => `.${d}`).join(",")}
                moTa={DINH_DANG_HO_TRO.join(", ")}
                tenFileDaChon={file?.name}
              />
            </div>
          ) : (
            <div>
              <label htmlFor="kb-noidung" className="mb-1.5 block text-small font-medium text-ink">
                Nội dung
              </label>
              <textarea
                id="kb-noidung"
                className="gc-input min-h-40 w-full resize-y leading-relaxed"
                value={noiDung}
                onChange={(e) => setNoiDung(e.target.value)}
                placeholder="Dán hoặc gõ nội dung cần bot tra cứu..."
              />
            </div>
          )}

          {error && <p className="text-small text-danger">{error}</p>}
        </div>

        <div className="border-t border-line px-5 py-4">
          <button
            onClick={() => void luu()}
            disabled={busy || !hopLe}
            className="w-full cursor-pointer rounded-control bg-brand-500 py-2.5 text-body font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Đang thêm..." : "Thêm nguồn"}
          </button>
        </div>
      </div>
    </div>
  );
}
