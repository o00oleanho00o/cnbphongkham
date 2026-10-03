// ported from: web/src/pages/agent-detail-page.tsx
"use client";

// Deviations: `useParams`/`useRouter`/`next/link`; the one-off error handed over by the create page
// (react-router location state in the original) is read from sessionStorage; the agent is still found in
// the list (the contract has no GET /admin/agents/{id} either); DTOs are `AgentOut`/`AgentUpdate`.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { useUnsavedChangesPrompt } from "@/lib/admin/shared/use-unsaved-changes-prompt";
import {
  kiemForm,
  thanhPatch,
  tuAgent,
  type AgentDetailForm,
} from "@/lib/admin/agents/agent-detail-form";
import { DUONG_DAN_DANH_SACH, khoTamCuaTab, layLoiSauKhiTao } from "@/lib/admin/agents/agent-draft";
import { AgentFormLayout } from "@/components/admin/agents/agent-form-layout";
import { AgentIdentitySection } from "@/components/admin/agents/agent-identity-section";
import { useAgentKbRefreshBridge } from "@/lib/admin/agents/agent-kb-refresh-bridge";

/**
 * Trang sửa một agent. Tách khỏi màn TẠO (`agent-create-modal.tsx`) vì hai việc
 * khác nhịp: tạo cần nhanh, sửa cần đủ chỗ cho model, công cụ (phase sau) và
 * ngân sách token.
 *
 * Cố ý dùng nút "Lưu thay đổi" chứ KHÔNG tự lưu như trang Cấu hình: ở đó mỗi ô
 * là một thiết lập độc lập, còn ở đây cả trang là MỘT bản ghi - `updateAgent`
 * ghi trọn dòng, nên lưu từng ô sẽ ghi đè cả những ô người dùng đang sửa dở.
 */
type ManagedAgent = Schemas["AgentOut"];

export default function AgentDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const router = useRouter();
  // Tạo xong thì về thẳng danh sách, KHÔNG qua đây. Đường duy nhất màn tạo đá
  // sang trang này là ca hiếm: agent đã tạo được nhưng nhịp PATCH phần model
  // hỏng - phải nói ra, kẻo tưởng mấy ô model vừa đặt đã được lưu.
  const [agent, setAgent] = useState<ManagedAgent | null>(null);
  const [form, setForm] = useState<AgentDetailForm | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState("");
  const [daLuu, setDaLuu] = useState(false);
  const [busy, setBusy] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();
  const { kbDirty, onKbDirtyChange, kbRefreshSignal, onKbSaved } = useAgentKbRefreshBridge();

  // Đọc một lần duy nhất (đọc xong là xóa) để F5 không hiện lại câu cũ
  useEffect(() => {
    const loiTruoc = layLoiSauKhiTao(khoTamCuaTab());
    if (loiTruoc) setLoi(loiTruoc);
  }, []);

  useEffect(() => {
    let huy = false;
    // Không có `GET /api/agents/:id` nên lọc từ danh sách - tránh đổi backend
    // chỉ để phục vụ một trang. Số agent luôn nhỏ (vài cái), không đáng thêm route.
    unwrap(http.GET("/api/v1/admin/agents"))
      .then((items) => {
        if (huy) return;
        const tim = items.find((a) => a.id === id) ?? null;
        setAgent(tim);
        setForm(tim ? tuAgent(tim) : null);
      })
      .catch(() => !huy && setAgent(null))
      .finally(() => !huy && setDangTai(false));
    return () => {
      huy = true;
    };
  }, [id]);

  const doi = (patch: Partial<AgentDetailForm>) => {
    setForm((f) => (f ? { ...f, ...patch } : f));
    setDaLuu(false);
    setLoi("");
  };

  const banDau = agent ? tuAgent(agent) : null;
  const coDoiForm = Boolean(form && banDau && JSON.stringify(form) !== JSON.stringify(banDau));
  // I17: khối Kho tri thức giữ state riêng (ngoài AgentDetailForm) - gộp dirty
  // vào chốt RỜI TRANG, KHÔNG gộp vào nút "Lưu thay đổi" (nút đó chỉ ghi form;
  // KB lưu qua nút riêng - gộp sẽ bật nhầm nút Lưu dù form chưa đổi gì).
  const coDoiRoiTrang = coDoiForm || kbDirty;

  /**
   * Một hộp thoại dùng cho MỌI đường rời trang - nút "Quay lại" lẫn sidebar.
   * Hai câu chữ khác nhau cho cùng một chuyện là cách chắc chắn để chúng trôi
   * khỏi nhau.
   *
   * `tone: "normal"` vì đây không phải hành động phá hủy; để mặc định "danger"
   * thì hộp thoại rời trang hiện nút đỏ kèm icon cảnh báo y như hộp thoại xóa.
   *
   * `useCallback` để tham chiếu ổn định: hàm này nằm trong deps của useEffect
   * đăng ký chốt, đổi tham chiếu mỗi lần render sẽ đăng ký lại liên tục.
   */
  const hoiRoiTrang = useCallback(
    () =>
      confirm({
        title: "Rời trang mà chưa lưu?",
        message: "Những thay đổi bạn vừa sửa trên trang này sẽ mất.",
        confirmLabel: "Rời đi",
        cancelLabel: "Ở lại",
        tone: "normal",
      }),
    [confirm],
  );

  useUnsavedChangesPrompt(coDoiRoiTrang, hoiRoiTrang);

  /** Rời trang bằng nút "Quay lại". Ô persona nhận tới 8000 ký tự - mất là mất thật. */
  async function roiTrang() {
    if (coDoiRoiTrang && !(await hoiRoiTrang())) return;
    router.push(DUONG_DAN_DANH_SACH);
  }

  async function luu() {
    if (!form || !agent) return;
    // Kiểm bằng đúng luật của `patchSchema` phía server. Chốt cũ
    // `!Number.isFinite(...)` là code chết: ô lúc đó là type="number" nên trình
    // duyệt đã nuốt chữ rác thành rỗng trước khi tới đây, `Number("")` ra 0 chứ
    // không bao giờ ra NaN. Hai ca thật (99 và 1.5) thì không ai chặn.
    const loiForm = kiemForm(form);
    if (loiForm) {
      setLoi(loiForm);
      return;
    }
    setBusy(true);
    setLoi("");
    try {
      const moi = await unwrap(
        http.PATCH("/api/v1/admin/agents/{agent_id}", {
          params: { path: { agent_id: agent.id } },
          body: thanhPatch(form),
        }),
      );
      // `account_count` là cột tính bằng subquery của danh sách; nếu PATCH trả bản ghi thô thì giữ số cũ,
      // kẻo dòng phụ đề lật thành "Chưa tài khoản nào dùng" ngay sau khi bấm Lưu.
      setAgent((cu) => ({ ...moi, account_count: moi.account_count ?? cu?.account_count ?? 0 }));
      setForm(tuAgent(moi));
      setDaLuu(true);
    } catch (err) {
      setLoi(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (dangTai) return <p className="text-ink-soft">Đang tải...</p>;

  if (!agent || !form) {
    return (
      <div>
        <PageHeader title="Không tìm thấy agent" subtitle={`Không có agent nào mang id "${id}"`} />
        <Link href="/admin/agents" className="text-body text-brand-600 hover:underline">
          Quay lại danh sách agent
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={form.name || agent.id}
        subtitle={
          (agent.account_count ?? 0) > 0
            ? `${agent.account_count} tài khoản Zalo đang dùng agent này`
            : "Chưa tài khoản nào dùng agent này"
        }
        aside={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={roiTrang}
              className="cursor-pointer rounded-control border border-line px-4 py-2 text-body font-medium text-ink-soft hover:bg-tile"
            >
              Quay lại
            </button>
            <button
              type="button"
              onClick={luu}
              disabled={busy || !coDoiForm || form.name.trim() === ""}
              className="cursor-pointer rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "Đang lưu..." : "Lưu thay đổi"}
            </button>
          </div>
        }
      />

      {loi && <p className="mb-4 text-small text-danger">{loi}</p>}
      {daLuu && !coDoiForm && <p className="mb-4 text-small text-success">Đã lưu thay đổi.</p>}

      <AgentFormLayout
        form={form}
        onChange={doi}
        soTaiKhoan={agent.account_count ?? 0}
        kb={{
          agentId: agent.id,
          onDirtyChange: onKbDirtyChange,
          onSaved: onKbSaved,
          refreshSignal: kbRefreshSignal,
        }}
        danhTinh={
          <AgentIdentitySection
            id={agent.id}
            isDefault={agent.is_default ?? false}
            form={form}
            onChange={doi}
          />
        }
      />

      {confirmDialog}
    </div>
  );
}
