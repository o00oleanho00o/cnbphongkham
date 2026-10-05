"use client";

// Kế hoạch tab: the treatment plans of the patient with their progress, and the old "Điều chỉnh kế hoạch" form
// (name and total number of sessions, never below what is done). Plans come from the Patient 360 read model; a
// plan's counter moves only when a session is completed (the BE does that).
import { useState, type FormEvent } from "react";

import { Fact, FormError, Muted } from "@/components/ops/patient/shared";
import { EmptyState } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { PatientOrdersCard } from "@/components/orders/patient-orders-card";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/ops/format";
import { PLAN_STATUS_LABEL } from "@/lib/ops/labels";
import {
  MAX_PLAN_SESSIONS,
  planStepStates,
  validatePlanForm,
  type PlanFormState,
} from "@/lib/ops/plan-form";
import { useSession } from "@/lib/session/session-context";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Sheet } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Plan = Schemas["TreatmentPlanOut"];
type PlanStatus = Schemas["PlanStatus"];

const STEP_TEXT = {
  done: {
    title: "Đã hoàn tất",
    detail: "Đã ghi nhận buổi và hướng dẫn chăm sóc.",
    chip: "Đã xong",
  },
  next: { title: "Tiếp theo", detail: "Cần đánh giá da trước khi thực hiện.", chip: "Sắp tới" },
  later: { title: "Dự kiến", detail: "Mốc dự kiến theo đáp ứng của người bệnh.", chip: "Chưa mở" },
} as const;

const STATUS_TONE: Record<PlanStatus, "brand" | "success" | "neutral"> = {
  planned: "neutral",
  active: "brand",
  completed: "success",
  abandoned: "neutral",
  cancelled: "neutral",
};

function isPlanStatus(value: string): value is PlanStatus {
  return value in PLAN_STATUS_LABEL;
}

function PlanDialog({
  patientId,
  plan,
  onClose,
  onSaved,
}: {
  patientId: string;
  /** The plan being edited, or undefined to create one. */
  plan: Plan | undefined;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<PlanFormState>({
    title: plan?.title ?? "",
    serviceCode: plan?.service_code ?? "",
    total: String(plan?.total_sessions ?? 3),
    goal: plan?.goal ?? "",
  });
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const patch = (change: Partial<PlanFormState>) =>
    setForm((current) => ({ ...current, ...change }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const message = validatePlanForm(form, plan?.completed_sessions ?? 0, plan === undefined);
    if (message !== null) {
      setProblem(message);
      return;
    }
    setBusy(true);
    setProblem("");
    const total = Number(form.total);
    try {
      if (plan === undefined) {
        await unwrap(
          http.POST("/api/v1/patients/{patient_id}/plans", {
            params: { path: { patient_id: patientId } },
            body: {
              title: form.title.trim(),
              service_code: form.serviceCode.trim(),
              total_sessions: total,
              goal: form.goal.trim() === "" ? null : form.goal.trim(),
            },
          }),
        );
      } else {
        await unwrap(
          http.PATCH("/api/v1/plans/{plan_id}", {
            params: { path: { plan_id: plan.id } },
            body: {
              version: plan.version ?? 1,
              title: form.title.trim(),
              total_sessions: total,
              goal: form.goal.trim() === "" ? null : form.goal.trim(),
            },
          }),
        );
      }
      toast.push("success", "Đã lưu kế hoạch.");
      onSaved();
      onClose();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={plan === undefined ? "Thêm kế hoạch" : "Điều chỉnh kế hoạch"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" form="plan-form" disabled={busy}>
            Lưu kế hoạch
          </Button>
        </>
      }
    >
      <form id="plan-form" onSubmit={(e) => void submit(e)} noValidate>
        <Field label="Tên kế hoạch" required>
          {(control) => (
            <input
              {...control}
              value={form.title}
              maxLength={120}
              onChange={(e) => patch({ title: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        {plan === undefined && (
          <Field label="Mã dịch vụ" hint="Ví dụ: laser-co2" required>
            {(control) => (
              <input
                {...control}
                value={form.serviceCode}
                maxLength={60}
                onChange={(e) => patch({ serviceCode: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        )}
        <Field
          label="Tổng số buổi dự kiến"
          hint={`Từ ${Math.max(1, plan?.completed_sessions ?? 1)} đến ${MAX_PLAN_SESSIONS} buổi.`}
          required
        >
          {(control) => (
            <input
              {...control}
              type="number"
              inputMode="numeric"
              min={Math.max(1, plan?.completed_sessions ?? 1)}
              max={MAX_PLAN_SESSIONS}
              value={form.total}
              onChange={(e) => patch({ total: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Mục tiêu điều trị">
          {(control) => (
            <textarea
              {...control}
              value={form.goal}
              maxLength={500}
              onChange={(e) => patch({ goal: e.target.value })}
              className={`${FIELD_CONTROL_CLASS} min-h-20 resize-y`}
            />
          )}
        </Field>
        <FormError message={problem} />
      </form>
    </Sheet>
  );
}

function PlanCard({
  plan,
  canWrite,
  onEdit,
}: {
  plan: Plan;
  canWrite: boolean;
  onEdit: () => void;
}) {
  const status = isPlanStatus(plan.status) ? plan.status : "active";
  const percent = Math.round((plan.completed_sessions / Math.max(1, plan.total_sessions)) * 100);
  const steps = planStepStates(plan.completed_sessions, plan.total_sessions);
  return (
    <Card
      title={plan.title}
      subtitle={`Kế hoạch ${PLAN_STATUS_LABEL[status].toLowerCase()} · mã ${plan.service_code}`}
      aside={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[status]} dot={false}>
            {PLAN_STATUS_LABEL[status]}
          </Badge>
          {canWrite && (
            <Button variant="secondary" onClick={onEdit}>
              Chỉnh sửa
            </Button>
          )}
        </div>
      }
    >
      <div className="rounded-control border border-line bg-tile/50 p-3">
        <h3 className="text-small font-semibold text-heading">Mục tiêu điều trị</h3>
        <p className="mt-1 text-small break-words text-ink-soft">
          {plan.goal ?? "Chưa ghi mục tiêu. Bác sĩ có thể thêm bằng nút Chỉnh sửa."}
        </p>
        <div className="mt-3 flex items-center gap-3">
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Tiến độ ${plan.title}`}
            className="h-2 min-w-0 flex-1 overflow-hidden rounded-pill bg-line"
          >
            <div className="h-full rounded-pill bg-brand-500" style={{ width: `${percent}%` }} />
          </div>
          <span className="text-small whitespace-nowrap text-ink-soft">
            {plan.completed_sessions}/{plan.total_sessions} buổi
          </span>
        </div>
      </div>
      <ol className="mt-3 space-y-2">
        {steps.map((state, index) => (
          <li
            key={index}
            className="flex items-start justify-between gap-3 rounded-control border border-line px-3 py-2.5"
          >
            <div className="min-w-0">
              <div className="text-small font-semibold text-ink">
                Buổi {index + 1} · {STEP_TEXT[state].title}
              </div>
              <div className="text-label text-ink-soft">{STEP_TEXT[state].detail}</div>
            </div>
            <Badge
              tone={state === "done" ? "success" : state === "next" ? "brand" : "neutral"}
              dot={false}
            >
              {STEP_TEXT[state].chip}
            </Badge>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function PlanTab({
  patientId,
  plans,
  doctorName,
  nextVisit,
  canWrite,
  onChanged,
}: {
  patientId: string;
  plans: Plan[];
  doctorName: string | null | undefined;
  /** Day of the next appointment, if there is one. */
  nextVisit: string | null | undefined;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [dialog, setDialog] = useState<{ plan: Plan | undefined } | null>(null);
  const { canAny } = useSession();
  const live = plans.filter((p) => p.status === "planned" || p.status === "active");
  const remaining = live.reduce(
    (sum, p) => sum + Math.max(0, p.total_sessions - p.completed_sessions),
    0,
  );

  return (
    <div className="space-y-4">
      {canWrite && (
        <div className="flex flex-wrap justify-end gap-2">
          <Button onClick={() => setDialog({ plan: undefined })}>Thêm kế hoạch</Button>
        </div>
      )}
      {plans.length === 0 ? (
        <EmptyState
          title="Chưa có kế hoạch điều trị"
          hint={canWrite ? "Thêm kế hoạch để ghi các buổi điều trị theo từng mốc." : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="min-w-0 space-y-4 lg:col-span-2">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                canWrite={canWrite}
                onEdit={() => setDialog({ plan })}
              />
            ))}
          </div>
          <Card title="Theo dõi">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 lg:grid-cols-1">
              <Fact label="Bác sĩ phụ trách" value={doctorName ?? "-"} />
              <Fact label="Buổi còn lại" value={`${remaining} buổi`} />
              <Fact
                label="Hẹn tiếp theo"
                value={nextVisit ? formatDate(nextVisit) : "Chưa đặt lịch"}
              />
            </dl>
            <div className="mt-3">
              <Muted>Số buổi chỉ tăng khi bác sĩ hoàn tất một buổi điều trị.</Muted>
            </div>
          </Card>
        </div>
      )}
      {canAny(["order.read", "order.write"]) && <PatientOrdersCard patientId={patientId} />}
      {dialog !== null && (
        <PlanDialog
          patientId={patientId}
          plan={dialog.plan}
          onClose={() => setDialog(null)}
          onSaved={onChanged}
        />
      )}
    </div>
  );
}
