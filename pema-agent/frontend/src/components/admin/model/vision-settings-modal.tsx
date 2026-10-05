// ported from: web/src/pages/vision-settings-modal.tsx
"use client";

// Deviations (contract `VisionSettingsOut` / `VisionSettingsUpdate`): the original had a `mode` for the main
// model (auto/on/off) and a sidecar. The contract exposes ONLY the sidecar (`enabled`, `provider`,
// `base_url`, `model`, `api_key`), so step 1 is informational (always tried first, nothing to set), the
// sidecar gets the `enabled` switch, and there is no "Test sidecar" (no such operation: open item).
// Images are a patient_channel hazard: the profile turns image tools off and flags patient photos for
// staff, which the intro says so nobody expects the sidecar to read patient photos there.
import { useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { SecretInput } from "@/components/admin/shared/secret-input";
import { SelectMenu } from "@/components/admin/shared/select-menu";
import {
  ChainStep,
  ModalField,
  modalButton,
  ToolModalShell,
} from "@/components/admin/tools/tool-settings-modal-shell";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type VisionSettings = Schemas["VisionSettingsOut"];
type LlmProviderKind = Schemas["LlmProviderKind"];

const PROVIDER_OPTIONS: { value: LlmProviderKind; label: string }[] = [
  { value: "openai-compatible", label: "OpenAI-compatible (Ollama, llama-server, router)" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google" },
];

export function VisionSettingsModal({
  vision,
  onClose,
  onSaved,
}: {
  vision: VisionSettings;
  onClose: () => void;
  onSaved: (next: VisionSettings) => void;
}) {
  const [enabled, setEnabled] = useState(vision.enabled);
  const [provider, setProvider] = useState<LlmProviderKind>(vision.provider ?? "openai-compatible");
  const [baseUrl, setBaseUrl] = useState(vision.base_url ?? "");
  const [model, setModel] = useState(vision.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ tone: "green" | "red"; text: string } | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const hasKey = Boolean(vision.api_key_masked);
  const hasSomethingToClear = hasKey || Boolean(vision.base_url) || Boolean(vision.model);

  async function save() {
    setBusy(true);
    setStatus(null);
    try {
      const res = await unwrap(
        http.PATCH("/api/v1/admin/model/vision", {
          body: {
            enabled,
            provider,
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
      setStatus({ tone: "red", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  async function clearSidecar() {
    // Mất key thật (phải xin lại từ nhà cung cấp) nên hỏi trước - cùng nếp với
    // xóa account/agent
    const ok = await confirm({
      title: "Xóa cấu hình?",
      message: "Cả API key cũng bị xóa. Bot sẽ không đọc được ảnh cho tới khi bạn cấu hình lại.",
    });
    if (!ok) return;
    setBusy(true);
    setStatus(null);
    try {
      await unwrap(http.DELETE("/api/v1/admin/model/vision/sidecar"));
      const next = await unwrap(http.GET("/api/v1/admin/model/vision"));
      onSaved(next);
      onClose();
    } catch (err) {
      setStatus({ tone: "red", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <ToolModalShell
        title="Đọc ảnh - chuỗi nguồn"
        subtitle="Model chính đọc pixel trước; không đọc được thì sidecar mô tả ảnh thành chữ."
        onClose={onClose}
        footer={
          <>
            {hasSomethingToClear && (
              <button
                type="button"
                onClick={clearSidecar}
                disabled={busy}
                className={`mr-auto ${modalButton.danger}`}
              >
                Xóa cấu hình sidecar
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
        <ChainStep
          index={1}
          title="Model chính tự đọc ảnh"
          description="Luôn thử trước nếu model có khả năng đọc ảnh. Không có gì để cài ở bậc này."
          enabled
          locked
        />

        <ChainStep
          index={2}
          title="Model sidecar mô tả ảnh"
          enabled={enabled}
          onToggle={() => setEnabled((v) => !v)}
        >
          <ModalField id="sidecar-provider" label="Nhà cung cấp">
            <SelectMenu
              id="sidecar-provider"
              size="md"
              value={provider}
              options={PROVIDER_OPTIONS}
              onChange={(v) => setProvider(v as LlmProviderKind)}
            />
          </ModalField>
          <ModalField id="sidecar-url" label="Base URL">
            <input
              id="sidecar-url"
              className="gc-input w-full"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://generativelanguage.googleapis.com/v1beta/openai"
            />
          </ModalField>
          <ModalField
            id="sidecar-model"
            label="Model"
            hint="Ví dụ một model có vision chạy trên máy phòng khám."
          >
            <input
              id="sidecar-model"
              className="gc-input w-full"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="qwen2.5-vl"
            />
          </ModalField>
          <ModalField id="sidecar-key" label="API key">
            <SecretInput
              id="sidecar-key"
              value={apiKey}
              onChange={setApiKey}
              placeholder={
                hasKey
                  ? `Hiện tại ${vision.api_key_masked} - bỏ trống để giữ`
                  : "Dán API key vào đây"
              }
            />
          </ModalField>
        </ChainStep>

        <div className="rounded-tile border border-warning-line bg-warning-soft px-4 py-2.5 text-label leading-[1.6] text-warning">
          Với hồ sơ chính sách Kênh bệnh nhân, công cụ đọc ảnh bị tắt và ảnh khách gửi được chuyển
          cho nhân viên xem: sidecar không đọc ảnh của bệnh nhân ở đó.
        </div>

        {status && (
          <div
            className={`rounded-tile border px-4 py-2.5 text-small ${
              status.tone === "green"
                ? "border-success-line bg-success-soft text-success"
                : "border-danger-line bg-danger-soft text-danger"
            }`}
          >
            {status.text}
          </div>
        )}
      </ToolModalShell>
      {confirmDialog}
    </>
  );
}
