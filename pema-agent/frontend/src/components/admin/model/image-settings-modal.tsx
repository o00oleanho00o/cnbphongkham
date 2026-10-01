// ported from: web/src/pages/image-settings-modal.tsx
"use client";

// Deviations (contract `ImageGenSettingsOut` / `ImageGenSettingsUpdate`, under /admin/tools/image-gen):
// the settings carry an `enabled` switch; there is no "Vẽ thử 1 ảnh" (the contract has no test
// operation: open item), so the model name cannot be checked from here and the hint says so.
// Image tools are off in the Kênh bệnh nhân policy profile whatever is set here.
import { useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { SecretInput } from "@/components/admin/shared/secret-input";
import { ToggleKnob } from "@/components/admin/shared/ui-bits";
import {
  ModalField,
  modalButton,
  ToolModalShell,
} from "@/components/admin/tools/tool-settings-modal-shell";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type ImageGenSettings = Schemas["ImageGenSettingsOut"];

/**
 * Modal cấu hình vẽ ảnh, mở từ nút Settings trên dòng tool "Vẽ ảnh AI".
 *
 * Không trình bày dạng chuỗi nhiều bậc như web_search/vision vì đây chỉ có MỘT
 * nguồn: không có bậc dự phòng nào để rơi xuống khi provider vẽ ảnh hỏng.
 */
export function ImageSettingsModal({
  settings,
  onClose,
  onSaved,
}: {
  settings: ImageGenSettings;
  onClose: () => void;
  onSaved: (next: ImageGenSettings) => void;
}) {
  const [enabled, setEnabled] = useState(settings.enabled);
  const [baseUrl, setBaseUrl] = useState(settings.base_url ?? "");
  const [model, setModel] = useState(settings.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { confirm, confirmDialog } = useConfirmDialog();

  const hasKey = Boolean(settings.api_key_masked);
  const hasSomethingToClear = hasKey || Boolean(settings.base_url) || Boolean(settings.model);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const res = await unwrap(
        http.PATCH("/api/v1/admin/tools/image-gen", {
          body: {
            enabled,
            base_url: baseUrl,
            model,
            // Bỏ trống = giữ key hiện tại (xóa key dùng nút riêng bên dưới)
            api_key: apiKey || undefined,
          },
        }),
      );
      onSaved(res);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function clearSettings() {
    // Mất key thật (phải xin lại từ nhà cung cấp) nên hỏi trước - cùng nếp với
    // xóa cấu hình sidecar
    const ok = await confirm({
      title: "Xóa cấu hình vẽ ảnh?",
      message: "Cả API key cũng bị xóa. Bot sẽ không vẽ được ảnh cho tới khi bạn cấu hình lại.",
    });
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      await unwrap(http.DELETE("/api/v1/admin/tools/image-gen"));
      const next = await unwrap(http.GET("/api/v1/admin/tools/image-gen"));
      onSaved(next);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ToolModalShell
        title="Vẽ ảnh AI"
        subtitle="Endpoint OpenAI-compatible /v1/images/generations - vẽ mới hoặc sửa ảnh người dùng gửi."
        onClose={onClose}
        footer={
          <>
            {hasSomethingToClear && (
              <button
                type="button"
                onClick={clearSettings}
                disabled={busy}
                className={`mr-auto ${modalButton.danger}`}
              >
                Xóa cấu hình
              </button>
            )}
            <button type="button" onClick={onClose} className={modalButton.cancel}>
              Hủy
            </button>
            <button type="button" onClick={save} disabled={busy} className={modalButton.primary}>
              {busy ? "Đang lưu..." : "Lưu"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[13px] font-medium text-ink">Bật vẽ ảnh</div>
              <div className="text-[12px] text-ink-soft">Tắt thì bot không có công cụ vẽ ảnh.</div>
            </div>
            <button
              type="button"
              aria-pressed={enabled}
              aria-label="Bật vẽ ảnh"
              onClick={() => setEnabled((v) => !v)}
              className="shrink-0"
            >
              <ToggleKnob on={enabled} />
            </button>
          </div>

          <ModalField
            id="image-base-url"
            label="Base URL"
            hint="Chỉ phần gốc, không kèm /v1/images/generations - bot tự nối."
          >
            <input
              id="image-base-url"
              className="gc-input w-full"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.example.com"
            />
          </ModalField>

          <ModalField
            id="image-model"
            label="Model"
            hint="Không có danh sách để chọn và chưa có nút vẽ thử: gõ đúng tên model của nhà cung cấp."
          >
            <input
              id="image-model"
              className="gc-input w-full"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-5.5-image"
            />
          </ModalField>

          <ModalField id="image-api-key" label="API key">
            <SecretInput
              id="image-api-key"
              value={apiKey}
              onChange={setApiKey}
              placeholder={
                hasKey
                  ? `Hiện tại ${settings.api_key_masked} - bỏ trống để giữ`
                  : "Dán API key vào đây"
              }
            />
          </ModalField>
        </div>

        <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-2.5 text-[12px] leading-[1.6] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
          Mỗi ảnh mất khoảng 1 phút và tốn phí của nhà cung cấp. Hồ sơ chính sách Kênh bệnh nhân tắt
          công cụ này bất kể cấu hình ở đây.
        </div>

        {error && (
          <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-2.5 text-[13px] text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}
      </ToolModalShell>
      {confirmDialog}
    </>
  );
}
