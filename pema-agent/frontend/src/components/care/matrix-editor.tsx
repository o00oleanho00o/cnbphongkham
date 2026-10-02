"use client";

// The depth and autonomy matrix: "hand off from depth X" per signal, the confidence thresholds, and per action type
// how many unchanged approvals lift it to L2. These numbers are the DOCTOR's decision (PLAN-AI01-M section 15.1):
// until a doctor approves them they are temporary defaults, shown with the badge "Chờ bác sĩ duyệt". Saving cells
// puts the badge back (whoever edits); only `can_approve` (doctor, manager, owner) may clear it. Cells that are
// always a person (a medical judgement, a birthday greeting) are shown but cannot be edited. The backend
// enforces all of this; the editor follows `can_edit` and `can_approve`.
import { useId, useMemo, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { SectionCard } from "@/components/admin/shared/ui-bits";
import { ApprovalBadge } from "@/components/care/care-ui";
import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { CareDepth, CareMatrix } from "@/lib/care/care-types";
import { DEPTHS } from "@/lib/care/care-types";
import { setAutonomyRule, setDepthRow, sameJson } from "@/lib/care/forms";
import { DEPTH_LABEL, SIGNAL_LABEL, actionTypeLabel } from "@/lib/care/labels";
import {
  buildMatrix,
  editOf,
  textOf,
  type MatrixEdit,
  type MatrixText,
} from "@/lib/care/matrix-draft";

const DEPTH_OPTIONS: SelectOption[] = DEPTHS.map((d) => ({ value: d, label: DEPTH_LABEL[d] }));

export function MatrixEditor({ matrix, onChanged }: { matrix: CareMatrix; onChanged: () => void }) {
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const baseId = useId();
  const [edit, setEdit] = useState<MatrixEdit>(() => editOf(matrix));
  const [text, setText] = useState<MatrixText>(() => textOf(matrix));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const readOnly = !matrix.can_edit;

  const built = useMemo(() => buildMatrix(matrix, edit, text), [matrix, edit, text]);
  const dirty = useMemo(
    () =>
      built.value === null ||
      !sameJson(
        { handoff: built.value.handoff, autonomy: built.value.autonomy },
        { handoff: matrix.handoff, autonomy: matrix.autonomy },
      ),
    [built, matrix],
  );

  function reset() {
    setEdit(editOf(matrix));
    setText(textOf(matrix));
    setError("");
  }

  async function save() {
    if (built.value === null) return;
    setBusy(true);
    setError("");
    try {
      await careApi.saveMatrix(built.value);
      toast.push("success", "Đã lưu ma trận. Ma trận quay lại trạng thái chờ bác sĩ duyệt.");
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve(approved: boolean) {
    const ok = await confirm({
      title: approved ? "Duyệt ma trận này?" : "Đặt lại về chờ duyệt?",
      message: approved
        ? "Các ngưỡng hiện tại được xác nhận là quyết định của bác sĩ. Hãy chắc rằng đã lưu mọi chỉnh sửa trước khi duyệt."
        : "Ma trận sẽ hiện lại nhãn chờ bác sĩ duyệt.",
      confirmLabel: approved ? "Duyệt" : "Đặt lại",
      tone: "normal",
    });
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      await careApi.approveMatrix(approved, matrix.version);
      toast.push("success", approved ? "Bác sĩ đã duyệt ma trận." : "Đã đặt lại về chờ duyệt.");
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ApprovalBadge pending={matrix.pending_doctor_approval} />
        <div className="flex flex-wrap gap-2">
          {matrix.can_approve && matrix.pending_doctor_approval && (
            <PrimaryButton disabled={busy || dirty} onClick={() => void approve(true)}>
              Bác sĩ duyệt
            </PrimaryButton>
          )}
          {matrix.can_approve && !matrix.pending_doctor_approval && (
            <SecondaryButton disabled={busy} onClick={() => void approve(false)}>
              Đặt lại chờ duyệt
            </SecondaryButton>
          )}
        </div>
      </div>
      {matrix.pending_doctor_approval && (
        <Notice tone="warn">
          Các số dưới đây là mặc định tạm thời. Bác sĩ quyết định ngưỡng cuối cùng; trước đó agent
          vẫn chạy theo các số này nhưng không coi là đã được duyệt.
        </Notice>
      )}
      {readOnly && <Notice tone="info">Bạn chỉ xem được ma trận, không chỉnh được.</Notice>}

      <SectionCard
        title="Khi nào agent nhờ người"
        subtitle="Từ độ sâu nào thì chuyển cho người, theo từng tín hiệu. Chọn mức thấp nhất áp dụng."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Ngưỡng tin cậy của agent"
            htmlFor={`${baseId}-hc`}
            hint="Dưới ngưỡng thì chuyển cho người (0 đến 1)"
          >
            <input
              id={`${baseId}-hc`}
              inputMode="decimal"
              className="gc-input w-28"
              disabled={readOnly}
              value={text.handoffConfidence}
              onChange={(e) => setText({ ...text, handoffConfidence: e.target.value })}
            />
          </Field>
          <Field label="Cửa sổ sau thủ thuật (giờ)" htmlFor={`${baseId}-pw`}>
            <input
              id={`${baseId}-pw`}
              inputMode="numeric"
              className="gc-input w-28"
              disabled={readOnly}
              value={text.windowHours}
              onChange={(e) => setText({ ...text, windowHours: e.target.value })}
            />
          </Field>
          <Field
            label="Số lần hỏi lặp lại"
            htmlFor={`${baseId}-rq`}
            hint="Hỏi cùng một câu từng này lần thì tính là lặp"
          >
            <input
              id={`${baseId}-rq`}
              inputMode="numeric"
              className="gc-input w-28"
              disabled={readOnly}
              value={text.repeatThreshold}
              onChange={(e) => setText({ ...text, repeatThreshold: e.target.value })}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Field
            label="Khách chưa xác minh danh tính chỉ được trả lời tới"
            htmlFor={`${baseId}-um`}
          >
            <div className="sm:w-72">
              <SelectMenu
                id={`${baseId}-um`}
                size="md"
                value={edit.handoff.unverified_max_depth}
                options={DEPTH_OPTIONS}
                disabled={readOnly}
                onChange={(v) =>
                  setEdit({
                    ...edit,
                    handoff: { ...edit.handoff, unverified_max_depth: v as CareDepth },
                  })
                }
              />
            </div>
          </Field>
        </div>
        <ul className="mt-4 divide-y divide-line">
          {edit.handoff.rows.map((row) => (
            <li key={row.signal} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-[14px] text-ink">{SIGNAL_LABEL[row.signal]}</span>
              <div className="w-full sm:w-64">
                <SelectMenu
                  ariaLabel={`Chuyển cho người từ độ sâu, tín hiệu ${SIGNAL_LABEL[row.signal]}`}
                  size="md"
                  value={row.from_depth}
                  options={DEPTH_OPTIONS}
                  disabled={readOnly}
                  onChange={(v) =>
                    setEdit({
                      ...edit,
                      handoff: setDepthRow(edit.handoff, row.signal, v as CareDepth),
                    })
                  }
                />
              </div>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard
        title="Agent được tự gửi gì"
        subtitle="Số lần bác sĩ duyệt mà không sửa trước khi một loại tin được lên L2"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Ngưỡng tin cậy để tự trả lời"
            htmlFor={`${baseId}-ac`}
            hint="L2 chỉ tự trả lời khi độ tin cậy từ ngưỡng này (0 đến 1)"
          >
            <input
              id={`${baseId}-ac`}
              inputMode="decimal"
              className="gc-input w-28"
              disabled={readOnly}
              value={text.autonomyConfidence}
              onChange={(e) => setText({ ...text, autonomyConfidence: e.target.value })}
            />
          </Field>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 self-end">
            <input
              type="checkbox"
              disabled={readOnly}
              checked={edit.autonomy.appointment_confirm_l1}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  autonomy: { ...edit.autonomy, appointment_confirm_l1: e.target.checked },
                })
              }
            />
            <span className="text-[14px] text-ink">Xác nhận lịch hẹn khách đã chọn chạy ở L1</span>
          </label>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-[14px]">
            <thead>
              <tr className="text-[12px] text-ink-soft">
                <th className="py-2 pr-3 font-medium">Loại tin</th>
                <th className="py-2 pr-3 font-medium">Lên L2 sau (lần)</th>
                <th className="py-2 font-medium">Mở cho D3</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {edit.autonomy.rules.map((rule) => (
                <tr key={rule.action_type}>
                  <td className="py-2 pr-3 text-ink">
                    {actionTypeLabel(rule.action_type)}
                    {rule.hard_human && (
                      <span className="block text-[12px] text-ink-soft">
                        Luôn do người quyết định, không chỉnh được
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <input
                      aria-label={`Lên L2 sau bao nhiêu lần, ${actionTypeLabel(rule.action_type)}`}
                      inputMode="numeric"
                      className="gc-input w-24"
                      disabled={readOnly || rule.hard_human}
                      value={text.nToL2[rule.action_type] ?? ""}
                      onChange={(e) =>
                        setText({
                          ...text,
                          nToL2: { ...text.nToL2, [rule.action_type]: e.target.value },
                        })
                      }
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="checkbox"
                      aria-label={`Mở cho D3, ${actionTypeLabel(rule.action_type)}`}
                      disabled={readOnly || rule.hard_human}
                      checked={rule.d3_enabled}
                      onChange={(e) =>
                        setEdit({
                          ...edit,
                          autonomy: setAutonomyRule(edit.autonomy, rule.action_type, {
                            d3_enabled: e.target.checked,
                          }),
                        })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {built.value === null && dirty && <Notice tone="warn">{built.error}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {!readOnly && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <PrimaryButton
            disabled={busy || !dirty || built.value === null}
            onClick={() => void save()}
          >
            Lưu ma trận
          </PrimaryButton>
          <SecondaryButton disabled={busy || !dirty} onClick={reset}>
            Bỏ thay đổi
          </SecondaryButton>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}
