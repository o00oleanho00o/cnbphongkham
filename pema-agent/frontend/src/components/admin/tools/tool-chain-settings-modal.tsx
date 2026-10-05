// ported from: web/src/pages/tool-chain-settings-modal.tsx
"use client";

// Deviations (contract `ToolChainSettings` / `ToolChainUpdate`): one settings object per tool with an
// ordered `steps` list (id, label, enabled) instead of the original `provider` (duckduckgo|brave) and the
// separate fetch flag. web_search: the Brave step is toggled through `steps`, its key goes up as
// `brave_api_key` ("" removes it) and only `brave_api_key_set` comes back (no masked value). web_fetch: the
// Jina step is `fallback_enabled`.

import { useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { SecretInput } from "@/components/admin/shared/secret-input";
import {
  ChainStep,
  modalButton,
  ToolModalShell,
} from "@/components/admin/tools/tool-settings-modal-shell";

type ToolCatalogItem = Schemas["ToolOut"];
type ToolChainSettings = Schemas["ToolChainSettings"];

/** Id of the Brave step in `steps` of web_search */
const BRAVE_STEP = "brave";

/**
 * Modal chuỗi nguồn của web_search / web_fetch.
 *
 * Bậc CUỐI của mỗi chuỗi khoá cứng (không có toggle) - đó là thứ bảo đảm tool
 * không bao giờ rơi vào trạng thái "chưa cấu hình": web_search luôn còn
 * DuckDuckGo, web_fetch luôn còn tầng tự tải.
 */
export function ToolChainSettingsModal({
  tool,
  settings,
  onClose,
  onSaved,
}: {
  tool: ToolCatalogItem;
  /** Current settings of THIS tool (web_search or web_fetch) */
  settings: ToolChainSettings;
  onClose: () => void;
  onSaved: (next: ToolChainSettings) => void;
}) {
  const isSearch = tool.key === "web_search";

  const steps = settings.steps ?? [];
  const [braveOn, setBraveOn] = useState(steps.find((x) => x.id === BRAVE_STEP)?.enabled ?? false);
  const [apiKey, setApiKey] = useState("");
  const [jinaOn, setJinaOn] = useState(settings.fallback_enabled ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { confirm, confirmDialog } = useConfirmDialog();

  const hasKey = settings.brave_api_key_set ?? false;
  const keyAvailable = hasKey || apiKey.trim().length > 0;
  const blocked = isSearch && braveOn && !keyAvailable;

  /** One PATCH per tool: the path differs, the body is the contract's `ToolChainUpdate` */
  function patchChain(body: Schemas["ToolChainUpdate"]) {
    return isSearch
      ? unwrap(http.PATCH("/api/v1/admin/tools/web_search", { body }))
      : unwrap(http.PATCH("/api/v1/admin/tools/web_fetch", { body }));
  }

  async function save() {
    if (blocked || saving) return;
    setSaving(true);
    setError("");
    try {
      const body = isSearch
        ? {
            steps: steps.map((x) => (x.id === BRAVE_STEP ? { ...x, enabled: braveOn } : x)),
            ...(apiKey.trim() ? { brave_api_key: apiKey.trim() } : {}),
          }
        : { fallback_enabled: jinaOn };
      const res = await patchChain(body);
      onSaved(res);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  /**
   * Gỡ hẳn key khỏi DB. Cần hành động riêng vì đường lưu quy ước "ô trống =
   * giữ key cũ" (để đổi cấu hình khác không phải nhập lại key), nên không có
   * cách nào gửi chuỗi rỗng qua nút Lưu.
   */
  async function clearBraveKey() {
    const ok = await confirm({
      title: "Xóa API key Brave?",
      message: "Web search sẽ chỉ còn DuckDuckGo (miễn phí) cho tới khi bạn nhập key mới.",
    });
    if (!ok) return;
    setSaving(true);
    setError("");
    try {
      // Xóa key thì provider tự hạ về duckduckgo ở tầng store
      const res = await patchChain({
        brave_api_key: "",
        steps: steps.map((x) => (x.id === BRAVE_STEP ? { ...x, enabled: false } : x)),
      });
      setApiKey("");
      setBraveOn(false);
      onSaved(res);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <ToolModalShell
        title={`${tool.label} - chuỗi nguồn`}
        subtitle="Thử lần lượt từ trên xuống, dừng ở bậc đầu tiên cho kết quả dùng được."
        onClose={onClose}
        footer={
          <>
            {isSearch && hasKey && (
              <button
                type="button"
                onClick={clearBraveKey}
                disabled={saving}
                className={`mr-auto ${modalButton.danger}`}
              >
                Xóa key Brave
              </button>
            )}
            <button type="button" onClick={onClose} className={modalButton.cancel}>
              Hủy
            </button>
            <button
              type="button"
              onClick={save}
              disabled={blocked || saving}
              className={modalButton.primary}
            >
              {saving ? "Đang lưu..." : "Lưu"}
            </button>
          </>
        }
      >
        {isSearch ? (
          <>
            <ChainStep
              index={1}
              title="Brave Search"
              description="Kết quả tốt hơn, cần API key. Hết quota hoặc lỗi thì tự rơi xuống bậc dưới."
              enabled={braveOn}
              onToggle={() => setBraveOn((v) => !v)}
            >
              <label className="block text-small font-medium text-ink" htmlFor="brave-key">
                API key
                <span className="ml-2 font-normal text-ink-soft">
                  ({hasKey ? "đã lưu key" : "chưa có key"})
                </span>
              </label>
              <SecretInput
                id="brave-key"
                value={apiKey}
                onChange={setApiKey}
                placeholder={hasKey ? "Để trống nếu giữ key cũ" : "Dán key vào đây"}
                className="mt-1.5"
              />
              <p className="mt-1.5 text-label leading-[1.6] text-ink-soft">
                Lấy key miễn phí tại{" "}
                <a
                  href="https://brave.com/search/api/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-600 hover:underline"
                >
                  brave.com/search/api
                </a>
                .
              </p>
            </ChainStep>

            <ChainStep
              index={2}
              title="DuckDuckGo"
              description="Miễn phí, không cần key. Là bậc cuối nên web search không bao giờ thiếu nguồn."
              enabled
              locked
            />

            {blocked && (
              <div className="rounded-tile border border-warning-line bg-warning-soft px-4 py-2.5 text-small text-warning">
                Nhập API key Brave trước rồi mới bật được bậc này.
              </div>
            )}
          </>
        ) : (
          <>
            <ChainStep
              index={1}
              title="Tự tải trực tiếp"
              description="Nhanh, riêng tư, đã chặn IP nội bộ chống SSRF. Không đọc được trang render bằng JavaScript."
              enabled
              locked
            />
            <ChainStep
              index={2}
              title="Jina Reader (r.jina.ai)"
              description="Dùng khi bậc 1 hỏng hoặc ra quá ít chữ: render được trang JavaScript, qua được một phần chặn bot. Chậm hơn nhiều và URL đi qua dịch vụ bên thứ ba."
              enabled={jinaOn}
              onToggle={() => setJinaOn((v) => !v)}
            />
          </>
        )}

        {error && (
          <div className="rounded-tile border border-danger-line bg-danger-soft px-4 py-2.5 text-small text-danger">
            {error}
          </div>
        )}
      </ToolModalShell>
      {confirmDialog}
    </>
  );
}
