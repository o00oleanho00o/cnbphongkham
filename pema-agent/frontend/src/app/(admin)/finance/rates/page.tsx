"use client";

// Chính sách tỷ lệ (old web: `finance.js` `rates()`): for every service the basis the commission is applied to
// (Giá sau giảm, Giá niêm yết, Theo thực thu) and the rate. A change makes a new version of the service terms and
// applies to the entries recorded after it: every entry keeps the rate it was recorded with. The rate lives on the
// service (`PATCH /services/{id}`, `admin.rules`); this screen is the accountant's door to it.
import { useCallback, useState, type FormEvent } from "react";

import { useFinance } from "@/components/finance/finance-context";
import { LoadState } from "@/components/finance/finance-ui";
import { Notice, SecondaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import { BASES, BASIS_LABEL, asBasis, type ServiceRow } from "@/lib/catalog/catalog-view";
import {
  RATE_PROBLEM,
  financeErrorMessage,
  percentTextToBp,
  rateChanged,
  rateFormOf,
  type RateForm,
} from "@/lib/finance/finance-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Card } from "@/ui/card";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

function RateRow({
  service,
  editable,
  onSaved,
}: {
  service: ServiceRow;
  editable: boolean;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<RateForm>(() => rateFormOf(service));
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const rate = percentTextToBp(form.rate);
    if (rate === null) {
      setProblem(RATE_PROBLEM);
      return;
    }
    if (!rateChanged(service, form)) {
      setProblem("");
      toast.push("info", "Tỷ lệ chưa đổi.");
      return;
    }
    setProblem("");
    setBusy(true);
    try {
      await unwrap(
        http.PATCH("/api/v1/services/{service_id}", {
          params: { path: { service_id: service.id } },
          body: { version: service.version, rate_bp: rate, basis: form.basis },
        }),
      );
      toast.push("success", "Đã ghi nhận thành công");
      onSaved();
    } catch (error) {
      setProblem(financeErrorMessage(error));
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void submit(event)}
      className="flex flex-wrap items-end justify-between gap-4 py-4"
      noValidate
      aria-label={`Chính sách ${service.name}`}
    >
      <div className="min-w-0">
        <p className="text-body font-semibold text-ink">{service.name}</p>
        <p className="text-small text-ink-soft">Phiên bản {service.terms_version}</p>
        {problem !== "" && (
          <p role="alert" className="mt-1 text-label text-danger">
            {problem}
          </p>
        )}
      </div>
      {editable ? (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Cơ sở" className="mb-0">
            {(control) => (
              <select
                {...control}
                value={form.basis}
                onChange={(e) => setForm({ ...form, basis: asBasis(e.target.value) })}
                className={FIELD_CONTROL_CLASS}
              >
                {BASES.map((basis) => (
                  <option key={basis} value={basis}>
                    {BASIS_LABEL[basis]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Tỷ lệ %" required className="mb-0">
            {(control) => (
              <input
                {...control}
                type="number"
                min={0}
                max={100}
                step={0.01}
                value={form.rate}
                onChange={(e) => setForm({ ...form, rate: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <SecondaryButton type="submit" disabled={busy}>
            Lưu tỷ lệ
          </SecondaryButton>
        </div>
      ) : (
        <p className="text-small text-ink-soft">Tỷ lệ chỉ hiển thị cho người quản lý danh mục.</p>
      )}
    </form>
  );
}

export default function FinanceRatesPage() {
  const { refreshKey } = useFinance();
  const { can } = useSession();
  const load = useCallback(
    (signal: AbortSignal): Promise<ServiceRow[]> => {
      void refreshKey; // "Làm mới" and every change raise it: a new load function means "fetch again"
      return unwrap(http.GET("/api/v1/services", { signal }));
    },
    [refreshKey],
  );
  const { data, error, loading, reload } = useLoad(load);

  return (
    <div className="space-y-4">
      <LoadState error={error} loading={loading} hasData={data !== undefined} onRetry={reload} />
      {data && (
        <Card title="Chính sách theo thủ thuật">
          <p className="mb-2 text-small text-ink-soft">
            Áp dụng cho lượt tạo sau khi lưu. Người phối hợp có thể được kế toán phân bổ riêng tại
            lượt thực hiện.
          </p>
          {data.length === 0 && <Notice>Chưa có thủ thuật nào.</Notice>}
          <div className="divide-y divide-line">
            {data.map((service) => (
              <RateRow
                key={`${service.id}:${service.version}`}
                service={service}
                editable={can("admin.rules") && service.rate_bp != null}
                onSaved={reload}
              />
            ))}
          </div>
          <p className="mt-2 text-small text-ink-soft">
            Cơ sở tính có 3 lựa chọn: Giá sau giảm · Giá niêm yết · Theo thực thu.
          </p>
        </Card>
      )}
    </div>
  );
}
