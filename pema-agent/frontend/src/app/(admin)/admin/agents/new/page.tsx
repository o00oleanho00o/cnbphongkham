// ported from: web/src/pages/agent-create-page.tsx
"use client";

// Deviations: the draft comes from sessionStorage (react-router location state does not exist, see
// agent-draft.ts); no draft = back to the list; the typed client replaces `api.agentsAdmin`; the create
// body carries the new `policy_profile`; a half-done create hands the error to the edit page through
// sessionStorage (`luuLoiSauKhiTao`).

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { useUnsavedChangesPrompt } from "@/lib/admin/shared/use-unsaved-changes-prompt";
import { kiemForm, thanhPatch, type AgentDetailForm } from "@/lib/admin/agents/agent-detail-form";
import {
  DUONG_DAN_DANH_SACH,
  canPatchSauKhiTao,
  docBanNhap,
  khoTamCuaTab,
  luuLoiSauKhiTao,
  tuBanNhap,
  xoaBanNhap,
  type BanNhapAgent,
} from "@/lib/admin/agents/agent-draft";
import { AgentFormLayout } from "@/components/admin/agents/agent-form-layout";
import { kiemDinhDangId } from "@/components/admin/agents/agent-id-field";
import { AgentIdentitySection } from "@/components/admin/agents/agent-identity-section";

/**
 * Bước 2 của việc tạo agent: cùng bố cục với trang sửa, nhưng CHƯA có gì trong
 * DB. Bấm "Tạo agent" mới ghi, bấm "Hủy" là bỏ hẳn.
 *
 * Bản nhập đi qua state của router chứ không qua URL: id chưa chốt (còn sửa
 * được ngay trên trang này) nên nhét vào đường dẫn là tự mâu thuẫn. Đổi lại,
 * F5 giữa chừng là mất bản nhập - nên vào thẳng đường dẫn này mà không có bản
 * nhập thì đá về danh sách thay vì hiện một form rỗng không rõ đang tạo cái gì.
 */
export default function AgentCreatePage() {
  const router = useRouter();
  const [banNhap, setBanNhap] = useState<BanNhapAgent | null | undefined>(undefined);

  // sessionStorage chỉ có ở trình duyệt: đọc sau khi mount
  useEffect(() => {
    const doc = docBanNhap(khoTamCuaTab());
    if (!doc) {
      router.replace(DUONG_DAN_DANH_SACH);
      return;
    }
    setBanNhap(doc);
  }, [router]);

  if (!banNhap) return null;
  return (
    <ManTao
      banNhap={banNhap}
      // Tạo xong về thẳng danh sách: mọi thứ đã lưu rồi, đứng lại ở trang sửa
      // chỉ tổ mời người ta bấm "Lưu thay đổi" một lần nữa cho cùng nội dung.
      // `replace` để nút Back không quay lại màn tạo của agent vừa tạo xong.
      onXong={() => {
        xoaBanNhap(khoTamCuaTab());
        router.replace(DUONG_DAN_DANH_SACH);
      }}
    />
  );
}

function ManTao({ banNhap, onXong }: { banNhap: BanNhapAgent; onXong: () => void }) {
  const router = useRouter();
  const [id, setId] = useState(banNhap.id);
  const [form, setForm] = useState<AgentDetailForm>(() => tuBanNhap(banNhap));
  const [loi, setLoi] = useState("");
  const [busy, setBusy] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();

  const doi = (patch: Partial<AgentDetailForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    setLoi("");
  };

  /**
   * Luôn hỏi khi rời trang: ở đây KHÔNG có bản gốc để so, mọi thứ trên màn hình
   * đều là thứ chưa từng được ghi. Rời đi là mất sạch, kể cả khi chưa gõ thêm
   * chữ nào so với lúc sang từ modal.
   */
  const hoiRoiTrang = useCallback(
    () =>
      confirm({
        title: "Bỏ agent đang tạo?",
        message: "Agent này chưa được tạo. Rời đi là mất những gì bạn vừa nhập.",
        confirmLabel: "Bỏ",
        cancelLabel: "Ở lại",
        tone: "normal",
      }),
    [confirm],
  );

  useUnsavedChangesPrompt(!busy, hoiRoiTrang);

  async function huy() {
    if (!(await hoiRoiTrang())) return;
    xoaBanNhap(khoTamCuaTab());
    router.push(DUONG_DAN_DANH_SACH);
  }

  async function tao() {
    const loiId = kiemDinhDangId(id) || (id.trim() === "" ? "ID không được để trống" : "");
    if (loiId) return setLoi(loiId);
    const loiForm = kiemForm(form);
    if (loiForm) return setLoi(loiForm);

    setBusy(true);
    setLoi("");
    try {
      const agent = await unwrap(
        http.POST("/api/v1/admin/agents", {
          body: {
            id,
            name: form.name.trim(),
            icon: form.icon,
            persona: form.persona,
            policy_profile: form.policyProfile,
          },
        }),
      );
      // POST không nhận model override lẫn tool tắt - xem `canPatchSauKhiTao`.
      // PATCH hỏng ở đây (vd trần context phạm ràng buộc chéo) thì agent ĐÃ tồn
      // tại: đẩy người dùng sang trang sửa kèm câu lỗi, chứ đứng lại đây thì
      // bấm Tạo lần nữa chỉ nhận 409 và không còn đường ra.
      if (canPatchSauKhiTao(form)) {
        try {
          await unwrap(
            http.PATCH("/api/v1/admin/agents/{agent_id}", {
              params: { path: { agent_id: agent.id } },
              body: thanhPatch(form),
            }),
          );
        } catch (err) {
          luuLoiSauKhiTao(khoTamCuaTab(), errorMessage(err));
          xoaBanNhap(khoTamCuaTab());
          router.replace(`/admin/agents/${encodeURIComponent(agent.id)}`);
          return;
        }
      }
      onXong();
    } catch (err) {
      setLoi(errorMessage(err));
      setBusy(false);
    }
  }

  const chuaDuDe = busy || form.name.trim() === "" || id.trim() === "" || form.icon.trim() === "";

  return (
    <div>
      <PageHeader
        title={form.name || "Agent mới"}
        subtitle="Chưa tạo - bấm Tạo agent để ghi lại, bấm Hủy là bỏ hẳn"
        aside={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={huy}
              className="rounded-control border border-line px-4 py-2 text-body font-medium text-ink-soft hover:bg-tile"
            >
              Hủy
            </button>
            <button
              type="button"
              onClick={tao}
              disabled={chuaDuDe}
              className="rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {busy ? "Đang tạo..." : "Tạo agent"}
            </button>
          </div>
        }
      />

      {loi && <p className="mb-4 text-small text-danger">{loi}</p>}

      <AgentFormLayout
        form={form}
        onChange={doi}
        soTaiKhoan={0}
        // Agent chưa tồn tại trong DB - chưa có id để gán nguồn Kho tri thức.
        // `null` TƯỜNG MINH (không phải bỏ trống 4 optional) - xem `KbFormBridge`.
        kb={null}
        danhTinh={
          <AgentIdentitySection
            id={id}
            isDefault={false}
            form={form}
            onChange={doi}
            onDoiId={(v) => {
              setId(v);
              setLoi("");
            }}
          />
        }
      />

      {confirmDialog}
    </div>
  );
}
