// ported from: web/src/pages/use-provider-form.ts

import { useEffect, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { baseUrlKhiLuu, oTheoNhaCungCap } from "@/lib/admin/model/provider-form-fields";

// Deviations: typed client over `LlmSettingsOut` / `LlmSettingsUpdate` (snake_case); the stored settings
// are mapped to the camelCase `CauHinhDaLuu` the pure field helpers expect.
type ProviderSettings = Schemas["LlmSettingsOut"];

export type ProviderForm = { provider: string; baseUrl: string; model: string; apiKey: string };
export type TrangThai = { tone: "green" | "red"; text: string } | null;

/**
 * Trạng thái + ba lời gọi API của form nhà cung cấp LLM (lưu, test kết nối,
 * xóa). Tách khỏi `providers-section.tsx` để file kia còn đúng phần hiển thị.
 */
export function useProviderForm() {
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [form, setForm] = useState<ProviderForm>({
    provider: "openai-compatible",
    baseUrl: "",
    model: "",
    apiKey: "",
  });
  const [status, setStatus] = useState<TrangThai>(null);
  const [busy, setBusy] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();

  const load = () =>
    unwrap(http.GET("/api/v1/admin/model/provider")).then((s) => {
      setSettings(s);
      setForm({
        provider: s.provider,
        baseUrl: s.base_url ?? "",
        model: s.model ?? "",
        apiKey: "",
      });
    });

  useEffect(() => {
    load().catch(() => setSettings(null));
  }, []);

  /**
   * Đổi "Kiểu kết nối" thì DỌN luôn hai ô thuộc về nhà cung cấp cũ.
   *
   * Trước đây ô này chỉ đổi mỗi `provider`, còn Model và Base URL giữ nguyên -
   * nên chọn Anthropic mà ô Model vẫn là `gemini-3.5-flash-lite`, bấm Lưu là
   * lưu được một tổ hợp vô nghĩa và bot chết ở lượt kế tiếp. Mỗi hãng một bộ
   * tên model, không có giá trị nào mang sang được.
   *
   * Quay VỀ nhà cung cấp đang lưu thì khôi phục nguyên giá trị đã lưu: bấm nhầm
   * rồi bấm lại là chuyện thường, bắt gõ lại tên model chỉ là ma sát.
   */
  function doiProvider(provider: string) {
    const daLuu = settings
      ? {
          provider: settings.provider,
          baseUrl: settings.base_url ?? "",
          model: settings.model ?? "",
        }
      : null;
    setForm({ ...form, provider, ...oTheoNhaCungCap(provider, daLuu) });
  }

  async function save() {
    setBusy(true);
    setStatus(null);
    try {
      await unwrap(
        http.PATCH("/api/v1/admin/model/provider", {
          body: {
            provider: form.provider as ProviderSettings["provider"],
            // `null` = XÓA hẳn. Base URL chỉ có nghĩa với openai-compatible; để lại
            // URL của nhà cũ thì nó nằm trong DB vĩnh viễn rồi hiện lại lúc quay về,
            // đọc ra như dashboard hỏng. Bỏ trống ở nhánh openai-compatible vẫn là
            // `undefined` (giữ nguyên) như cũ.
            base_url: baseUrlKhiLuu(form.provider, form.baseUrl),
            model: form.model,
            api_key: form.apiKey || undefined,
          },
        }),
      );
      await load();
      setStatus({
        tone: "green",
        text: "Đã lưu - áp dụng từ lượt agent kế tiếp, không cần restart",
      });
    } catch (err) {
      setStatus({ tone: "red", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setStatus(null);
    const result = await unwrap(http.POST("/api/v1/admin/model/provider/test")).catch(
      (err: unknown) => ({
        ok: false as const,
        error: errorMessage(err),
        reply: undefined,
      }),
    );
    setStatus(
      result.ok
        ? { tone: "green", text: `Kết nối ok - model trả lời: "${result.reply}"` }
        : { tone: "red", text: `Kết nối lỗi: ${result.error}` },
    );
    setBusy(false);
  }

  async function reset() {
    // Hành động PHÁ HỦY: `clearLlmSettings` xóa cả API key. Từ khi .env rút còn
    // 9 biến, phần LLM ở đó thường trống - nên không có bản dự phòng nào để
    // "quay về", bấm nhầm là bot câm ngay lượt sau. Mọi hành động phá hủy khác
    // trong dashboard đều hỏi trước; chỗ này trước đó thì không.
    const ok = await confirm({
      title: "Xóa toàn bộ cấu hình LLM?",
      message:
        "API key, base URL và tên model đã lưu sẽ bị xóa. Nếu máy chủ không đặt sẵn cấu hình LLM bằng biến môi trường thì bot ngừng trả lời cho tới khi bạn nhập lại.",
    });
    if (!ok) return;

    setBusy(true);
    try {
      await unwrap(http.DELETE("/api/v1/admin/model/provider"));
      await load();
      setStatus({ tone: "green", text: "Đã xóa cấu hình LLM đã lưu" });
    } catch (err) {
      // Thiếu `finally` là lỗi cũ ở đúng hàm này: request hỏng thì `busy` kẹt
      // `true` và cả ba nút Lưu/Test/Xóa không bấm được nữa cho tới khi F5
      setStatus({ tone: "red", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return { settings, form, setForm, doiProvider, status, busy, save, test, reset, confirmDialog };
}
