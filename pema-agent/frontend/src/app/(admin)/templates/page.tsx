"use client";

// Tin nhắn mẫu đã duyệt (`clinic.message_template`): the only texts a scheduled message may send to a
// patient in patient_channel. A person drafts, a DOCTOR approves (`review.decide_clinical`); editing clears
// the approval. Routes: `/api/v1/admin/templates`.
import { useCallback, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { IconFileText, IconPlus } from "@/components/admin/shared/dashboard-icons";
import { Badge } from "@/components/admin/shared/ui-bits";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
  SecondaryButton,
} from "@/components/ops/ops-ui";
import { TemplateSheet } from "@/components/ops/templates/template-sheet";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/ops/format";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

type Template = Schemas["MessageTemplateOut"];

export default function TemplatesPage() {
  const { can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [editing, setEditing] = useState<Template | "new" | null>(null);

  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/admin/templates", { signal })),
    [],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data ?? [], [data]);

  const canManage = can("kb.manage");
  const canApprove = can("review.decide_clinical");

  const closeSheet = useCallback(() => setEditing(null), []);
  const saved = useCallback(() => {
    setEditing(null);
    reload();
  }, [reload]);

  async function approve(t: Template) {
    const ok = await confirm({
      title: "Duyệt mẫu này?",
      message: `Bạn xác nhận nội dung mẫu "${t.title}" đúng và an toàn để gửi cho khách. Mẫu sẽ được bật ngay.`,
      confirmLabel: "Duyệt mẫu",
      tone: "normal",
    });
    if (!ok) return;
    try {
      await unwrap(
        http.POST("/api/v1/admin/templates/{template_id}/approve", {
          params: { path: { template_id: t.id } },
          body: { version: t.version },
        }),
      );
      toast.push("success", "Đã duyệt mẫu.");
    } catch (e) {
      toast.push(
        "error",
        e instanceof ApiError && e.code === "version_conflict"
          ? "Mẫu vừa được sửa. Đã tải lại."
          : errorMessage(e),
      );
    }
    reload();
  }

  async function toggleActive(t: Template) {
    try {
      await unwrap(
        http.PATCH("/api/v1/admin/templates/{template_id}", {
          params: { path: { template_id: t.id } },
          body: { active: !t.active, version: t.version },
        }),
      );
      toast.push("success", t.active ? "Đã tắt mẫu." : "Đã bật mẫu.");
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
    reload();
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        icon={IconFileText}
        title="Tin nhắn mẫu đã duyệt"
        subtitle="Văn bản bác sĩ đã duyệt, được dùng cho tin chăm sóc chủ động"
        aside={
          canManage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <IconPlus size={16} />
              Soạn mẫu mới
            </PrimaryButton>
          ) : undefined
        }
      />

      <div className="mb-4">
        <Notice>
          Mẫu mới hoặc vừa sửa chưa được dùng cho đến khi bác sĩ duyệt. Tin quảng bá không gửi cho
          khách đã từ chối quảng bá, và sinh nhật không bao giờ tự động gửi.
        </Notice>
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && items.length === 0 && (
        <EmptyState title="Chưa có mẫu nào" hint="Soạn mẫu đầu tiên và nhờ bác sĩ duyệt." />
      )}

      <ul className="grid gap-3 lg:grid-cols-2">
        {items.map((t) => (
          <li key={t.id} className="gc-card flex flex-col p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-ink">{t.title}</h2>
                <p className="font-mono text-[11px] text-ink-soft">{t.template_key}</p>
              </div>
              <div className="flex flex-wrap justify-end gap-1.5">
                {t.approved_at ? (
                  <Badge tone="green" dot={false}>
                    Bác sĩ đã duyệt
                  </Badge>
                ) : (
                  <Badge tone="amber" dot={false}>
                    Chờ bác sĩ duyệt
                  </Badge>
                )}
                {t.marketing && (
                  <Badge tone="gray" dot={false}>
                    Quảng bá
                  </Badge>
                )}
              </div>
            </div>
            <p className="mt-3 flex-1 rounded-lg bg-tile/60 px-3 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap text-ink">
              {t.body}
            </p>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[12px] text-ink-soft">
                {t.approved_at ? `Duyệt ${formatDate(t.approved_at)}` : "Chưa duyệt"} ·{" "}
                {t.active ? "Đang bật" : "Đang tắt"}
              </span>
              <div className="flex flex-wrap gap-2">
                {canApprove && !t.approved_at && (
                  <PrimaryButton onClick={() => void approve(t)}>Duyệt</PrimaryButton>
                )}
                {canManage && t.approved_at && (
                  <SecondaryButton onClick={() => void toggleActive(t)}>
                    {t.active ? "Tắt mẫu" : "Bật mẫu"}
                  </SecondaryButton>
                )}
                {canManage && <SecondaryButton onClick={() => setEditing(t)}>Sửa</SecondaryButton>}
              </div>
            </div>
          </li>
        ))}
      </ul>

      {editing && (
        <TemplateSheet
          template={editing === "new" ? null : editing}
          onClose={closeSheet}
          onSaved={saved}
        />
      )}
      {confirmDialog}
    </div>
  );
}
