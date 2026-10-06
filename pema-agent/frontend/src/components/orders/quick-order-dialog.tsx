"use client";

// "Tạo đơn thuốc / phiếu tư vấn": the quick order. Old web: `order-ui.js` `open()` (patient, doctor, diagnosis, the
// product search over the Excel catalog, the lines with quantity, sheet, usage, note and the reason for a changed
// sheet, the total, the general advice and the notice). The catalog is served by the backend
// (`GET /api/v1/catalog/products`, accents ignored); a draft is saved with `POST /api/v1/orders` (new) or
// `PUT /api/v1/orders/{id}` (the draft read at `version`). Name, unit and price of a line come from the catalog or
// from the draft's own snapshot: they are never typed here. The page then opens the review of the two sheets.
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  ROUTES,
  ROUTE_LABEL,
  addProduct,
  asRoute,
  catalogLine,
  draftFromOrder,
  draftTotal,
  emptyDraft,
  formatVnd,
  orderErrorMessage,
  orderStale,
  parseDraft,
  patchLine,
  productLine,
  removeLine,
  QUANTITY_BOUNDS,
  type DraftLine,
  type DraftOrder,
  type OrderRow,
  type ProductRow,
} from "@/lib/orders/order-view";
import { useLoad } from "@/lib/use-load";
import type { Schemas } from "@/lib/api";
import { Card } from "@/ui/card";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type PatientRow = Schemas["PatientOut"];
type DoctorChoice = { id: string; name: string };

const SEARCH_DELAY_MS = 200;
const PRODUCT_PAGE = 200;

type Lists = {
  patients: PatientRow[];
  doctors: DoctorChoice[];
  summary: Schemas["CatalogSummaryOut"];
};

function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

export function QuickOrderDialog({
  presetPatientId,
  editing,
  onClose,
  onSaved,
  onStale,
}: {
  /** the order starts for this patient (entry from Patient 360) */
  presetPatientId?: string;
  /** a draft to edit; null = a new order */
  editing: OrderRow | null;
  onClose: () => void;
  onSaved: (order: OrderRow) => void;
  /** the list on screen is out of date (stale version, order gone): reload it */
  onStale: () => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<DraftOrder>(() =>
    editing ? draftFromOrder(editing) : emptyDraft(presetPatientId ?? ""),
  );
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const search = useDebounced(query);

  const loadLists = useCallback(
    async (signal: AbortSignal): Promise<Lists> => {
      const [patients, resources, summary] = await Promise.all([
        unwrap(http.GET("/api/v1/patients", { params: { query: { limit: 200 } }, signal })),
        unwrap(http.GET("/api/v1/resources", { signal })),
        unwrap(http.GET("/api/v1/catalog/summary", { signal })),
      ]);
      const wanted = editing?.patient_id ?? presetPatientId;
      const known = patients.items.some((p) => p.id === wanted);
      const extra =
        wanted && !known
          ? await unwrap(
              http.GET("/api/v1/patients/{patient_id}", {
                params: { path: { patient_id: wanted } },
                signal,
              }),
            ).catch(() => null)
          : null;
      const doctors = resources.doctors
        .filter((d) => d.active)
        .map((d) => ({ id: d.user_id, name: d.name }));
      return {
        patients: extra ? [extra, ...patients.items] : patients.items,
        doctors,
        summary,
      };
    },
    [editing, presetPatientId],
  );
  const lists = useLoad(loadLists);

  const loadProducts = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/catalog/products", {
          params: { query: { q: search, limit: PRODUCT_PAGE } },
          signal,
        }),
      ),
    [search],
  );
  const products = useLoad(loadProducts);

  const doctors = useMemo(() => {
    const base = lists.data?.doctors ?? [];
    if (!editing || base.some((d) => d.id === editing.doctor_id)) return base;
    return [{ id: editing.doctor_id, name: editing.doctor_name }, ...base];
  }, [lists.data, editing]);

  // The first patient and doctor of a new order: the preset one, else the first in the list.
  useEffect(() => {
    if (editing || !lists.data) return;
    setDraft((current) => {
      const patientId = current.patientId || lists.data?.patients[0]?.id || "";
      const patient = lists.data?.patients.find((p) => p.id === patientId);
      const doctorId =
        current.doctorId ||
        doctors.find((d) => d.id === patient?.doctor_id)?.id ||
        doctors[0]?.id ||
        "";
      return patientId === current.patientId && doctorId === current.doctorId
        ? current
        : { ...current, patientId, doctorId };
    });
  }, [editing, lists.data, doctors]);

  const set = <K extends keyof DraftOrder>(key: K, value: DraftOrder[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const setLines = (next: DraftLine[]) => set("lines", next);

  function changePatient(patientId: string) {
    const patient = lists.data?.patients.find((p) => p.id === patientId);
    const doctorId = doctors.find((d) => d.id === patient?.doctor_id)?.id ?? draft.doctorId;
    setDraft((current) => ({ ...current, patientId, doctorId }));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    const parsed = parseDraft(draft);
    if (!parsed.ok) {
      setError(parsed.problem);
      return;
    }
    if (draft.patientId === "") {
      setError("Chọn bệnh nhân.");
      return;
    }
    setBusy(true);
    try {
      const common = {
        doctor_id: draft.doctorId || null,
        diagnosis: draft.diagnosis.trim(),
        note: draft.note.trim(),
        items: parsed.items,
      };
      const saved = editing
        ? await unwrap(
            http.PUT("/api/v1/orders/{order_id}", {
              params: { path: { order_id: editing.id } },
              body: { ...common, version: editing.version },
            }),
          )
        : await unwrap(
            http.POST("/api/v1/orders", { body: { ...common, patient_id: draft.patientId } }),
          );
      toast.push("success", "Đã lưu nháp. Kiểm tra hai phiếu trước khi duyệt.");
      onSaved(saved);
    } catch (err) {
      setError(orderErrorMessage(err));
      if (orderStale(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  const total = draftTotal(draft.lines);
  return (
    <Sheet
      title={editing ? "Sửa đơn nháp" : "Tạo đơn thuốc / phiếu tư vấn"}
      subtitle="Lên đơn từ danh mục Excel"
      onClose={onClose}
      xwide
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="quick-order-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Lưu nháp & xem tách đơn"}
          </PrimaryButton>
        </>
      }
    >
      <form id="quick-order-form" onSubmit={(e) => void save(e)} noValidate>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field label="Bệnh nhân">
            {(control) => (
              <select
                {...control}
                value={draft.patientId}
                onChange={(e) => changePatient(e.target.value)}
                disabled={editing !== null}
                className={FIELD_CONTROL_CLASS}
              >
                {(lists.data?.patients ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name} · {p.code}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Bác sĩ phụ trách">
            {(control) => (
              <select
                {...control}
                value={draft.doctorId}
                onChange={(e) => set("doctorId", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              >
                {doctors.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
        <Field label="Chẩn đoán / nội dung tư vấn">
          {(control) => (
            <input
              {...control}
              value={draft.diagnosis}
              onChange={(e) => set("diagnosis", e.target.value)}
              maxLength={2000}
              autoComplete="off"
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.85fr)]">
          <section aria-label="Danh mục sản phẩm" className="min-w-0">
            <Field label="Tìm mã hoặc tên sản phẩm">
              {(control) => (
                <input
                  {...control}
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ví dụ: H002, Cicaderm, TPCN"
                  autoComplete="off"
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            {lists.data && (
              <p className="mb-3 text-label text-ink-soft">{catalogLine(lists.data.summary)}</p>
            )}
            <ProductList
              products={products.data?.items}
              loading={products.loading && !products.data}
              error={products.error}
              onAdd={(product) => setLines(addProduct(draft.lines, product))}
            />
          </section>

          <Card
            title="Nội dung đơn"
            subtitle="Nhập cách dùng trước khi bác sĩ duyệt"
            className="min-w-0"
          >
            <CartLines lines={draft.lines} onChange={setLines} />
            <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3">
              <span className="text-small text-ink-soft">Tổng tiền dự kiến</span>
              <strong className="text-body-lg text-heading tabular-nums">{formatVnd(total)}</strong>
            </div>
          </Card>
        </div>

        <div className="mt-3.5">
          <Field label="Dặn dò chung">
            {(control) => (
              <textarea
                {...control}
                value={draft.note}
                onChange={(e) => set("note", e.target.value)}
                rows={2}
                maxLength={2000}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        </div>
        <Notice>
          Sản phẩm chưa có loại trong Excel cần được phân loại. “Không in” chỉ loại khỏi phiếu, vẫn
          tính trong hóa đơn. Đơn nháp chưa xuất hiện trên app.
        </Notice>
        {error !== "" && (
          <div className="mt-3" id="quick-error">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
      </form>
    </Sheet>
  );
}

function ProductList({
  products,
  loading,
  error,
  onAdd,
}: {
  products: readonly ProductRow[] | undefined;
  loading: boolean;
  error: string;
  onAdd: (product: ProductRow) => void;
}) {
  if (error !== "") return <Notice tone="error">{error}</Notice>;
  if (loading) return <p className="text-small text-ink-soft">Đang tải danh mục...</p>;
  if (products?.length === 0) {
    return <p className="text-small text-ink-soft">Không tìm thấy sản phẩm phù hợp.</p>;
  }
  return (
    <ul className="max-h-80 divide-y divide-line overflow-y-auto rounded-tile border border-line">
      {(products ?? []).map((product) => (
        <li key={product.code}>
          <button
            type="button"
            onClick={() => onAdd(product)}
            aria-label={`Thêm ${product.name}`}
            className="flex w-full items-start justify-between gap-3 px-3 py-2 text-left hover:bg-tile"
          >
            <span className="min-w-0">
              <strong className="block text-small text-ink">{product.name}</strong>
              <small className="block text-label text-ink-soft">{productLine(product)}</small>
            </span>
            <b className="shrink-0 text-small text-heading tabular-nums">
              {formatVnd(product.price_vnd)}
            </b>
          </button>
        </li>
      ))}
    </ul>
  );
}

function CartLines({
  lines,
  onChange,
}: {
  lines: readonly DraftLine[];
  onChange: (next: DraftLine[]) => void;
}) {
  if (lines.length === 0) {
    return <p className="text-small text-ink-soft">Chọn sản phẩm ở danh sách.</p>;
  }
  return (
    <div className="space-y-4">
      {lines.map((line, index) => (
        <article
          key={line.code}
          aria-label={`Dòng ${index + 1}`}
          className="border-b border-line pb-3 last:border-0"
        >
          <div className="flex items-start justify-between gap-3">
            <strong className="min-w-0 text-small text-ink">
              {index + 1}. {line.name}
            </strong>
            <button
              type="button"
              onClick={() => onChange(removeLine(lines, index))}
              aria-label={`Xóa ${line.code}`}
              className="rounded-control border border-line-strong px-2.5 py-1 text-small text-ink hover:bg-tile"
            >
              ×
            </button>
          </div>
          <p className="mb-2 text-label text-ink-soft">
            {line.code} · {line.unit} · {formatVnd(line.unitPrice)}
          </p>
          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <Field label={`Số lượng (${line.unit})`} required>
              {(control) => (
                <input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={QUANTITY_BOUNDS.min}
                  max={QUANTITY_BOUNDS.max}
                  step={1}
                  value={line.quantity}
                  onChange={(e) => onChange(patchLine(lines, index, { quantity: e.target.value }))}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            <Field label="Loại phiếu">
              {(control) => (
                <select
                  {...control}
                  value={line.route}
                  onChange={(e) =>
                    onChange(patchLine(lines, index, { route: asRoute(e.target.value) }))
                  }
                  className={FIELD_CONTROL_CLASS}
                >
                  {ROUTES.map((route) => (
                    <option key={route} value={route}>
                      {ROUTE_LABEL[route]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Field label="Cách dùng / tần suất / thời gian">
            {(control) => (
              <textarea
                {...control}
                value={line.usage}
                onChange={(e) => onChange(patchLine(lines, index, { usage: e.target.value }))}
                placeholder="Nhập hướng dẫn đã được bác sĩ chỉ định"
                rows={2}
                maxLength={2000}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Ghi chú sản phẩm">
            {(control) => (
              <input
                {...control}
                value={line.note}
                onChange={(e) => onChange(patchLine(lines, index, { note: e.target.value }))}
                maxLength={1000}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Lý do đổi phân loại (nếu có)" className="mb-0">
            {(control) => (
              <input
                {...control}
                value={line.routeReason}
                onChange={(e) => onChange(patchLine(lines, index, { routeReason: e.target.value }))}
                maxLength={500}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        </article>
      ))}
    </div>
  );
}
