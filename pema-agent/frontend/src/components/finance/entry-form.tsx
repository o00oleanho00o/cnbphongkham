"use client";

// "+ Ghi nhận lượt thủ thuật đã hoàn tất" (old web: `finance.js` `entryForm()`): a collapsible form that records a
// performed procedure for the accountant to approve. Who performed it is chosen here ("Bác sĩ chính", "Người phối
// hợp (tùy chọn)") and is never taken from the doctor in charge of the patient; the shares of the revenue must add up
// to 100 % and the rates to at most 100 %. Percent boxes are converted to basis points, the service decides the
// price and the rate to start from, and the rate is frozen on the entry by the BE (a later change of policy moves
// nothing). The patient comes from the patients API (search by name or code).
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import type { ServiceRow } from "@/lib/catalog/catalog-view";
import {
  emptyEntryForm,
  financeErrorMessage,
  invoiceChoiceLabel,
  parseEntryForm,
  patchPerson,
  withService,
  type Doctor,
  type EntryForm,
  type InvoiceRow,
} from "@/lib/finance/finance-view";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type PatientRow = Schemas["PatientOut"];

const SEARCH_DELAY_MS = 250;
const SEARCH_LIMIT = 20;

function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

/** One select of patients fed by a search box (name or code); the chosen one stays in the list. */
function PatientPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (patientId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<PatientRow[]>([]);
  const [chosen, setChosen] = useState<PatientRow | null>(null);
  const [problem, setProblem] = useState("");
  const search = useDebounced(query.trim());

  useEffect(() => {
    const controller = new AbortController();
    unwrap(
      http.GET("/api/v1/patients", {
        params: { query: { q: search === "" ? undefined : search, limit: SEARCH_LIMIT } },
        signal: controller.signal,
      }),
    )
      .then((page) => {
        setFound(page.items);
        setProblem("");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setProblem(financeErrorMessage(error));
      });
    return () => controller.abort();
  }, [search]);

  const options = useMemo(
    () => (chosen && !found.some((p) => p.id === chosen.id) ? [chosen, ...found] : found),
    [chosen, found],
  );

  return (
    <>
      <Field label="Tìm hồ sơ" className="mb-2">
        {(control) => (
          <input
            {...control}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tên hoặc mã hồ sơ"
            className={FIELD_CONTROL_CLASS}
            autoComplete="off"
          />
        )}
      </Field>
      <Field
        label="Hồ sơ"
        hint="Một lựa chọn cho mỗi hồ sơ"
        error={problem === "" ? undefined : problem}
        required
      >
        {(control) => (
          <select
            {...control}
            value={value}
            onChange={(e) => {
              const next = options.find((p) => p.id === e.target.value) ?? null;
              setChosen(next);
              onChange(e.target.value);
            }}
            className={FIELD_CONTROL_CLASS}
          >
            <option value="">Chọn hồ sơ</option>
            {options.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.full_name} · {patient.code}
              </option>
            ))}
          </select>
        )}
      </Field>
    </>
  );
}

function PersonRow({
  index,
  form,
  doctors,
  onChange,
}: {
  index: 0 | 1;
  form: EntryForm;
  doctors: readonly Doctor[];
  onChange: (next: EntryForm) => void;
}) {
  const person = form.people[index];
  return (
    <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <Field label={index === 0 ? "Bác sĩ chính" : "Người phối hợp (tùy chọn)"}>
        {(control) => (
          <select
            {...control}
            value={person.doctorId}
            onChange={(e) => onChange(patchPerson(form, index, { doctorId: e.target.value }))}
            className={FIELD_CONTROL_CLASS}
          >
            {index === 1 && <option value="">Không có</option>}
            {doctors.map((doctor) => (
              <option key={doctor.id} value={doctor.id}>
                {doctor.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Tỷ trọng doanh số %">
        {(control) => (
          <input
            {...control}
            type="number"
            min={0}
            max={100}
            step={0.01}
            value={person.share}
            onChange={(e) => onChange(patchPerson(form, index, { share: e.target.value }))}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
      <Field label="Tỷ lệ tiền thủ thuật %">
        {(control) => (
          <input
            {...control}
            type="number"
            min={0}
            max={100}
            step={0.01}
            value={person.rate}
            onChange={(e) => onChange(patchPerson(form, index, { rate: e.target.value }))}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
    </div>
  );
}

export function EntryFormPanel({
  today,
  services,
  doctors,
  invoices,
  defaultOpen,
  onSaved,
}: {
  today: string;
  services: readonly ServiceRow[];
  doctors: readonly Doctor[];
  invoices: readonly InvoiceRow[];
  defaultOpen: boolean;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(defaultOpen);
  const [form, setForm] = useState<EntryForm>(() =>
    emptyEntryForm(today, services[0], doctors[0]?.id ?? ""),
  );
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const attachable = invoices.filter((invoice) => invoice.patient_id === form.patientId);

  function chooseService(serviceId: string) {
    const service = services.find((s) => s.id === serviceId);
    setForm(service ? withService(form, service) : { ...form, serviceId });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseEntryForm(form, today);
    if (!parsed.ok) {
      setProblem(parsed.problem);
      return;
    }
    setProblem("");
    setBusy(true);
    try {
      await unwrap(http.POST("/api/v1/finance/entries", { body: parsed.body }));
      toast.push("success", "Đã ghi nhận thành công");
      setForm(emptyEntryForm(today, services[0], doctors[0]?.id ?? ""));
      setOpen(false);
      onSaved();
    } catch (error) {
      setProblem(financeErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {problem !== "" && (
        <div id="entry-error">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
      <details
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
        className="rounded-card border border-line bg-surface p-4 shadow-card sm:p-5"
      >
        <summary className="cursor-pointer text-body-lg font-bold text-heading">
          + Ghi nhận lượt thủ thuật đã hoàn tất
        </summary>
        <form onSubmit={(event) => void submit(event)} className="mt-4" noValidate>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2 xl:grid-cols-3">
            <div>
              <PatientPicker
                value={form.patientId}
                onChange={(patientId) => setForm({ ...form, patientId, invoiceId: "" })}
              />
            </div>
            <Field label="Thủ thuật">
              {(control) => (
                <select
                  {...control}
                  value={form.serviceId}
                  onChange={(e) => chooseService(e.target.value)}
                  className={FIELD_CONTROL_CLASS}
                >
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Ngày thực hiện" hint="Không chọn ngày sau hôm nay" required>
              {(control) => (
                <input
                  {...control}
                  type="date"
                  value={form.date}
                  max={today}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            <Field label="Giá niêm yết" required>
              {(control) => (
                <input
                  {...control}
                  type="number"
                  min={1}
                  step={1}
                  value={form.list}
                  onChange={(e) => setForm({ ...form, list: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            <Field label="Giảm giá" required>
              {(control) => (
                <input
                  {...control}
                  type="number"
                  min={0}
                  step={1}
                  value={form.discount}
                  onChange={(e) => setForm({ ...form, discount: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
            <Field label="Gắn hóa đơn đã có" hint="Hoặc một hóa đơn đã có của hồ sơ">
              {(control) => (
                <select
                  {...control}
                  value={form.invoiceId}
                  onChange={(e) => setForm({ ...form, invoiceId: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                >
                  <option value="">Tạo hóa đơn mới cho lượt này</option>
                  {attachable.map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      {invoiceChoiceLabel(invoice)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Ghi chú hoàn tất" required>
              {(control) => (
                <input
                  {...control}
                  value={form.note}
                  placeholder="Đã thực hiện, chờ đối soát"
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                  autoComplete="off"
                />
              )}
            </Field>
          </div>
          <h3 className="mt-2 text-body-lg font-bold text-heading">
            Ai thực hiện và được ghi nhận?
          </h3>
          <p className="mb-3 text-small text-ink-soft">
            Tổng tỷ trọng doanh số 100%. Tỷ lệ tiền của mỗi người tính trực tiếp trên cơ sở chính
            sách; tổng không quá 100%.
          </p>
          <PersonRow index={0} form={form} doctors={doctors} onChange={setForm} />
          <PersonRow index={1} form={form} doctors={doctors} onChange={setForm} />
          <PrimaryButton type="submit" disabled={busy}>
            {busy ? "Đang ghi..." : "Ghi nhận • Chờ duyệt"}
          </PrimaryButton>
        </form>
      </details>
    </div>
  );
}
