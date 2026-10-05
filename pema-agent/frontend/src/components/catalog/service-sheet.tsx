"use client";

// Add or edit a service (`POST /api/v1/services`, `PATCH /api/v1/services/{service_id}`). Old web: "Chỉnh dịch vụ"
// (`operations-ui.js` `service`): name, minutes of treatment, minutes of room preparation, price, active; the
// finance screen added the commission rate and its basis. Here they share one form. Only the owner and the
// manager reach it (`admin.rules`); the commission terms are the same people's.
//
// A change of price, rate, basis or duration starts a NEW snapshot of the terms: bookings and finance entries
// made before keep the old ones. The form says so before it is saved; the backend does the versioning.
import { useState, type FormEvent } from "react";

import { Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  BASES,
  BASIS_LABEL,
  SERVICE_BOUNDS,
  SERVICE_CODE_HINT,
  asBasis,
  buildServiceCreate,
  buildServiceUpdate,
  catalogErrorMessage,
  catalogStale,
  emptyServiceForm,
  formFromService,
  parseServiceForm,
  startsNewVersion,
  type ProtocolRow,
  type RoomRow,
  type ServiceForm,
  type ServiceRow,
} from "@/lib/catalog/catalog-view";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

export function ServiceSheet({
  service,
  rooms,
  protocols,
  withRate,
  onClose,
  onSaved,
  onStale,
}: {
  /** null = add a new service */
  service: ServiceRow | null;
  rooms: readonly RoomRow[];
  protocols: readonly ProtocolRow[];
  /** the caller sees and sets the commission terms (rate and basis) */
  withRate: boolean;
  onClose: () => void;
  onSaved: () => void;
  /** the list on screen is out of date (stale version, service gone): reload it */
  onStale: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<ServiceForm>(() =>
    service ? formFromService(service) : emptyServiceForm(),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const creating = service === null;

  const set = <K extends keyof ServiceForm>(key: K, value: ServiceForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));
  const toggleRoom = (id: string) =>
    set(
      "roomIds",
      form.roomIds.includes(id) ? form.roomIds.filter((r) => r !== id) : [...form.roomIds, id],
    );

  const preview = (() => {
    if (!service) return null;
    const parsed = parseServiceForm(form, { create: false, withRate });
    if (!parsed.ok) return null;
    const body = buildServiceUpdate(service, parsed.value, withRate);
    return body && startsNewVersion(body) ? service.terms_version + 1 : null;
  })();

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    const parsed = parseServiceForm(form, { create: creating, withRate });
    if (!parsed.ok) {
      setError(parsed.problem);
      return;
    }
    setBusy(true);
    try {
      if (service === null) {
        await unwrap(
          http.POST("/api/v1/services", { body: buildServiceCreate(parsed.value, form.code) }),
        );
        toast.push("success", "Đã thêm dịch vụ.");
      } else {
        const body = buildServiceUpdate(service, parsed.value, withRate);
        if (body === null) {
          toast.push("info", "Không có thay đổi nào để lưu.");
          onClose();
          return;
        }
        await unwrap(
          http.PATCH("/api/v1/services/{service_id}", {
            params: { path: { service_id: service.id } },
            body,
          }),
        );
        toast.push(
          "success",
          startsNewVersion(body)
            ? "Đã lưu dịch vụ. Điều khoản mới áp dụng cho lịch tạo sau đó."
            : "Đã lưu dịch vụ.",
        );
      }
      onSaved();
    } catch (err) {
      setError(catalogErrorMessage(err));
      if (catalogStale(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={creating ? "Thêm dịch vụ" : "Chỉnh dịch vụ"}
      subtitle={
        creating
          ? "Giá và thời lượng dùng cho lịch mới."
          : "Lịch đã đặt giữ giá và thời lượng tại lúc đặt."
      }
      onClose={onClose}
      wide
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="service-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Lưu dịch vụ"}
          </PrimaryButton>
        </>
      }
    >
      <form id="service-form" onSubmit={(e) => void save(e)} noValidate>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field
            label="Mã dịch vụ"
            hint={creating ? SERVICE_CODE_HINT : undefined}
            required={creating}
          >
            {(control) => (
              <input
                {...control}
                value={form.code}
                onChange={(e) => set("code", e.target.value)}
                disabled={!creating}
                maxLength={40}
                autoComplete="off"
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Tên dịch vụ" required>
            {(control) => (
              <input
                {...control}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                maxLength={120}
                autoComplete="off"
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field
            label="Điều trị (phút)"
            hint={`${SERVICE_BOUNDS.durationMin.min}-${SERVICE_BOUNDS.durationMin.max} phút`}
          >
            {(control) => (
              <input
                {...control}
                type="number"
                inputMode="numeric"
                value={form.duration}
                onChange={(e) => set("duration", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field
            label="Chuẩn bị phòng (phút)"
            hint={`${SERVICE_BOUNDS.bufferMin.min}-${SERVICE_BOUNDS.bufferMin.max} phút, phòng vẫn bị giữ`}
          >
            {(control) => (
              <input
                {...control}
                type="number"
                inputMode="numeric"
                value={form.buffer}
                onChange={(e) => set("buffer", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Giá (VND)">
            {(control) => (
              <input
                {...control}
                type="number"
                inputMode="numeric"
                value={form.price}
                onChange={(e) => set("price", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Giao thức theo dõi sau thủ thuật">
            {(control) => (
              <select
                {...control}
                value={form.protocolCode}
                onChange={(e) => set("protocolCode", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              >
                <option value="">Không có</option>
                {protocols.map((p) => (
                  <option key={p.id} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {withRate && (
            <>
              <Field
                label="Tiền thủ thuật (% của cơ sở tính)"
                hint="0-100, tối đa hai chữ số thập phân"
              >
                {(control) => (
                  <input
                    {...control}
                    inputMode="decimal"
                    value={form.rate}
                    onChange={(e) => set("rate", e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  />
                )}
              </Field>
              <Field label="Cơ sở tính">
                {(control) => (
                  <select
                    {...control}
                    value={form.basis}
                    onChange={(e) => set("basis", asBasis(e.target.value))}
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
            </>
          )}
        </div>

        <fieldset className="mb-3.5">
          <legend className="mb-1.5 block text-label font-semibold text-ink-soft">
            Phòng dùng được
          </legend>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {rooms.map((room) => (
              <label
                key={room.id}
                className="inline-flex min-h-9 items-center gap-2 text-body text-ink"
              >
                <input
                  type="checkbox"
                  checked={form.roomIds.includes(room.id)}
                  onChange={() => toggleRoom(room.id)}
                  className="h-4 w-4 accent-brand-500"
                />
                {room.name}
                {!room.active && <span className="text-label text-ink-soft">(tạm ngưng)</span>}
              </label>
            ))}
            {rooms.length === 0 && (
              <span className="text-small text-ink-soft">Chưa có phòng nào.</span>
            )}
          </div>
        </fieldset>

        <label className="mb-3.5 inline-flex min-h-9 items-center gap-2 text-body text-ink">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => set("active", e.target.checked)}
            className="h-4 w-4 accent-brand-500"
          />
          Đang dùng (bỏ chọn để tạm ngưng, không đặt lịch mới được)
        </label>

        {preview !== null && (
          <div className="mb-3">
            <Notice tone="info">
              Thay đổi này tạo phiên bản điều khoản {preview}. Lịch và hóa đơn đã tạo giữ điều khoản
              cũ.
            </Notice>
          </div>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
