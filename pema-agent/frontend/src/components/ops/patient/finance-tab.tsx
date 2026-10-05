"use client";

// "Dịch vụ & tài chính" tab of Patient 360 (old web: `crm-ui.js` `financial()` and the linked panels of
// `care-finance.js`; screens WC10, WC19, WC25, WC27, WC29). Three cards:
//   Hóa đơn của <tên>       the invoices of this patient (finance.read or finance.collect), "Mở thu ngân →"
//   Dịch vụ & liệu trình    the courses with sessions used, the price FIXED when the service was added, and
//                           "＋ Thêm dịch vụ" (finance.write: owner, manager, the accountant of U11)
//   Đơn thuốc               the orders of the patient (order.read); "＋ Tạo đơn nháp" opens the cashier
// Amounts the backend does not send (a role without a finance permission) are not drawn. Completed treatment is
// never inferred from a payment, and a payment is never read as medicine dispensed (AGENT.md).
// Not here, on purpose: the deposit ledger ("Tiền cọc đã phân bổ") has no table in this system, so the old
// notice about unallocated deposits is not shown; invoices are not linked to one course, so "Đã thu" is on the
// invoice rows and not on a course card.
import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";

import { EmptyState, ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { FormError } from "@/components/ops/patient/shared";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import {
  NO_INVOICES,
  formatVnd,
  invoiceKind,
  invoiceLine,
  type InvoiceRow,
} from "@/lib/finance/finance-view";
import {
  MAX_SERVICE_SESSIONS,
  parseServicePlanForm,
  planStatusLine,
  type ServicePlanForm,
} from "@/lib/ops/patient-profile";
import { historyLine } from "@/lib/orders/order-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { Sheet } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";
import { EmptyRow, TableShell } from "@/ui/table-shell";

type P360 = Schemas["Patient360"];
type Plan = Schemas["TreatmentPlanOut"];

const INVOICE_HEADERS = ["Hóa đơn", "Dịch vụ", "Phát sinh", "Đã thu", "Còn lại"];
const INVOICE_FETCH_LIMIT = 100;
const ADDED_COPY =
  "Giá đã chốt được lưu trên hồ sơ; thay đổi danh mục sau này không làm đổi liệu trình đã đăng ký.";

// ------------------------------------------------------------------------------------------- invoices
function InvoicesCard({ data, canCashier }: { data: P360; canCashier: boolean }) {
  const patientId = data.patient.id;
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/finance/invoices", {
          params: { query: { patient_id: patientId, limit: INVOICE_FETCH_LIMIT } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data: page, error, loading, reload } = useLoad(load);
  const rows: readonly InvoiceRow[] = page?.items ?? [];
  return (
    <Card
      title={`Hóa đơn của ${data.patient.full_name}`}
      subtitle="Giá trị phát sinh, tiền đã thu và dư nợ; không suy hoàn tất điều trị"
      aside={
        canCashier ? (
          <Link href="/cashier" className={buttonClass("secondary")}>
            Mở thu ngân →
          </Link>
        ) : undefined
      }
    >
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && page === undefined && <ListSkeleton rows={2} />}
      {page !== undefined && (
        <>
          <TableShell headers={INVOICE_HEADERS} minWidth={640}>
            {rows.length === 0 && <EmptyRow colSpan={INVOICE_HEADERS.length} text={NO_INVOICES} />}
            {rows.map((invoice) => (
              <tr key={invoice.id} className="border-b border-line align-top last:border-0">
                <td className="px-4 py-3">
                  <div className="text-body font-semibold text-ink">{invoice.number}</div>
                  <div className="text-small text-ink-soft">{invoiceLine(invoice)}</div>
                </td>
                <td className="px-4 py-3 text-body text-ink">{invoiceKind(invoice)}</td>
                <td className="px-4 py-3 text-body text-ink tabular-nums">
                  {formatVnd(invoice.amount_vnd)}
                </td>
                <td className="px-4 py-3 text-body text-ink tabular-nums">
                  {formatVnd(invoice.received_vnd)}
                </td>
                <td className="px-4 py-3 text-body text-ink tabular-nums">
                  {formatVnd(invoice.due_vnd)}
                </td>
              </tr>
            ))}
          </TableShell>
          <p className="mt-2 text-label text-ink-soft">{page.total} hóa đơn của hồ sơ này</p>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------- add a service to a course
function AddServiceDialog({
  patientId,
  onClose,
  onSaved,
}: {
  patientId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(http.GET("/api/v1/services", { params: { query: { active: true } }, signal })),
    [],
  );
  const { data: services, error, loading, reload } = useLoad(load);
  const [form, setForm] = useState<ServicePlanForm>({
    serviceId: "",
    sessions: "3",
    discount: "0",
  });
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const patch = (change: Partial<ServicePlanForm>) =>
    setForm((current) => ({ ...current, ...change }));
  const serviceId = form.serviceId === "" ? (services?.at(0)?.id ?? "") : form.serviceId;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = parseServicePlanForm({ ...form, serviceId });
    if (!parsed.ok) {
      setProblem(parsed.problem);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/service-plans", {
          params: { path: { patient_id: patientId } },
          body: parsed.body,
        }),
      );
      toast.push("success", "Đã thêm dịch vụ vào liệu trình");
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
      title="Thêm dịch vụ vào liệu trình"
      subtitle="Patient 360 · dịch vụ"
      onClose={onClose}
      footer={
        <Button type="submit" form="service-plan-form" disabled={busy || services === undefined}>
          Lưu dịch vụ
        </Button>
      }
    >
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && services === undefined && <ListSkeleton rows={2} />}
      {services !== undefined && (
        <form id="service-plan-form" onSubmit={(e) => void submit(e)} noValidate>
          <Field label="Dịch vụ">
            {(control) => (
              <select
                {...control}
                value={serviceId}
                onChange={(e) => patch({ serviceId: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              >
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name} · {formatVnd(service.price_vnd)}/buổi
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <Field label="Số buổi" hint={`Từ 1 đến ${MAX_SERVICE_SESSIONS} buổi.`}>
              {(control) => (
                <input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={MAX_SERVICE_SESSIONS}
                  value={form.sessions}
                  onChange={(e) => patch({ sessions: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            <Field label="Giảm giá (₫)">
              {(control) => (
                <input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  value={form.discount}
                  onChange={(e) => patch({ discount: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
          </div>
          <Notice>{ADDED_COPY}</Notice>
          <FormError message={problem} />
        </form>
      )}
    </Sheet>
  );
}

// ------------------------------------------------------------------------------------------------ plans
function PlanLine({ plan }: { plan: Plan }) {
  const percent = Math.min(
    100,
    Math.round((plan.completed_sessions / Math.max(1, plan.total_sessions)) * 100),
  );
  return (
    <article className="rounded-card border border-line bg-tile/50 p-3.5">
      <p className="text-eyebrow font-semibold tracking-wider text-ink-soft uppercase">
        Liệu trình · {plan.service_code}
      </p>
      <h3 className="mt-1 text-section font-semibold break-words text-heading">{plan.title}</h3>
      <p className="mt-1 text-small text-ink">
        <strong>
          {plan.completed_sessions}/{plan.total_sessions} buổi
        </strong>
        {plan.agreed_price_vnd !== null && plan.agreed_price_vnd !== undefined
          ? ` · ${formatVnd(plan.agreed_price_vnd)} sau giảm`
          : ""}
      </p>
      {plan.unit_price_vnd !== null && plan.unit_price_vnd !== undefined && (
        <p className="text-label text-ink-soft">
          {formatVnd(plan.unit_price_vnd)}/buổi
          {plan.discount_vnd ? ` · giảm ${formatVnd(plan.discount_vnd)}` : ""}
        </p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <Badge tone={plan.status === "completed" ? "success" : "info"} dot={false}>
          {planStatusLine(plan.status)}
        </Badge>
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
      </div>
    </article>
  );
}

function PlansCard({
  data,
  canAdd,
  canCashier,
  onChanged,
}: {
  data: P360;
  canAdd: boolean;
  canCashier: boolean;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const plans = data.plans ?? [];
  return (
    <Card
      title="Dịch vụ & liệu trình"
      subtitle="Giá chốt, số buổi và liên kết thu ngân"
      aside={canAdd ? <Button onClick={() => setAdding(true)}>＋ Thêm dịch vụ</Button> : undefined}
    >
      {plans.length === 0 && <EmptyState title="Chưa có dịch vụ gắn với hồ sơ." />}
      <div className="space-y-3">
        {plans.map((plan) => (
          <PlanLine key={plan.id} plan={plan} />
        ))}
      </div>
      {canCashier && (
        <div className="mt-3">
          <Link href="/cashier" className={buttonClass("quiet")}>
            Mở thu ngân →
          </Link>
        </div>
      )}
      {adding && (
        <AddServiceDialog
          patientId={data.patient.id}
          onClose={() => setAdding(false)}
          onSaved={onChanged}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------------------- prescriptions
function PrescriptionsCard({ patientId, canDraft }: { patientId: string; canDraft: boolean }) {
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/orders", {
          params: { query: { patient_id: patientId, limit: 20 } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const orders = data?.items ?? [];
  return (
    <Card
      title="Đơn thuốc"
      subtitle="Chỉ đơn đã duyệt mới xuất hiện trên Patient Mobile"
      aside={
        canDraft ? (
          <Link href={`/cashier?patient=${patientId}`} className={buttonClass("secondary")}>
            ＋ Tạo đơn nháp
          </Link>
        ) : undefined
      }
    >
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && data === undefined && <ListSkeleton rows={2} />}
      {data !== undefined && orders.length === 0 && <EmptyState title="Chưa có đơn thuốc." />}
      <ul className="divide-y divide-line">
        {orders.map((order) => (
          <li key={order.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="text-small text-ink">{historyLine(order)}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={order.status === "approved" ? "success" : "warning"} dot={false}>
                {order.status === "approved" ? "Đã duyệt" : "Chờ duyệt"}
              </Badge>
              <Link href={`/orders/${order.id}`} className={buttonClass("secondary")}>
                Xem / in
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function FinanceTab({ data, onChanged }: { data: P360; onChanged: () => void }) {
  const { can } = useSession();
  const canCashier = can("finance.collect");
  const canInvoices = canCashier || can("finance.read");
  return (
    <div className="space-y-4">
      {canInvoices && <InvoicesCard data={data} canCashier={canCashier} />}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <PlansCard
          data={data}
          canAdd={can("finance.write")}
          canCashier={canCashier}
          onChanged={onChanged}
        />
        {can("order.read") && (
          <PrescriptionsCard patientId={data.patient.id} canDraft={can("order.write")} />
        )}
      </div>
      {!canInvoices && (
        <Notice>
          Hóa đơn và thu tiền do lễ tân, kế toán hoặc chủ phòng khám phụ trách; vai trò của bạn
          không xem số tiền.
        </Notice>
      )}
    </div>
  );
}
