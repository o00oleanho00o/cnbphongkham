/** A small form for the services and the dates a source is in force. */
import { useEffect, useState } from "react";

import { knowledge } from "../client";
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { Service, Source, SourcePatch } from "../types";
import { periodError, toggled } from "./detail-logic";

export function MetaForm({
  source,
  busy,
  onSave,
  onCancel,
}: {
  source: Source;
  busy: boolean;
  onSave: (patch: SourcePatch) => void;
  onCancel: () => void;
}) {
  const [services, setServices] = useState<readonly string[]>(source.services);
  const [from, setFrom] = useState(source.effective_from ?? "");
  const [to, setTo] = useState(source.effective_to ?? "");
  const [catalog, setCatalog] = useState<Service[]>([]);
  const [catalogError, setCatalogError] = useState(false);

  useEffect(() => {
    let stale = false;
    knowledge.services().then(
      (found) => !stale && setCatalog(found),
      () => !stale && setCatalogError(true),
    );
    return () => {
      stale = true;
    };
  }, []);

  const problem = periodError(from, to);
  // A code the source holds that the catalog no longer lists stays selectable, so saving does not drop it silently.
  const known = new Set(catalog.map((service) => service.code));
  const orphans = source.services.filter((code) => !known.has(code));

  return (
    <div className="space-y-4 rounded-tile border border-line p-4">
      <fieldset>
        <legend className="mb-1.5 text-label font-semibold text-ink-soft">Dịch vụ liên quan</legend>
        {catalogError && <ui.Notice tone="warning">Không tải được danh mục dịch vụ.</ui.Notice>}
        <div className="flex flex-wrap gap-2">
          {catalog.map((service) => (
            <ServiceToggle
              key={service.code}
              label={service.name}
              code={service.code}
              checked={services.includes(service.code)}
              onChange={() => setServices(toggled(services, service.code))}
            />
          ))}
          {orphans.map((code) => (
            <ServiceToggle
              key={code}
              label={code}
              code={code}
              checked={services.includes(code)}
              onChange={() => setServices(toggled(services, code))}
            />
          ))}
        </div>
        <p className="mt-1 text-label text-ink-soft">Để trống: máy tự nhận diện dịch vụ.</p>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <ui.Field label="Hiệu lực từ ngày">
          <ui.Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </ui.Field>
        <ui.Field label="Đến ngày" hint="Để trống: không hạn." error={problem ?? undefined}>
          <ui.Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </ui.Field>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <ui.Button variant="secondary" onClick={onCancel}>
          Hủy
        </ui.Button>
        <ui.Button
          disabled={problem !== null}
          busy={busy}
          onClick={() => onSave({ services: [...services], effective_from: from || null, effective_to: to || null })}
        >
          Lưu
        </ui.Button>
      </div>
    </div>
  );
}

function ServiceToggle({
  label,
  code,
  checked,
  onChange,
}: {
  label: string;
  code: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3 text-small sm:min-h-0 sm:py-1 ${
        checked ? "border-link bg-tile text-link" : "border-line text-ink"
      }`}
    >
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
      <span className="text-micro text-ink-soft">{code}</span>
    </label>
  );
}

/** The services of a source as chips, or a line saying they are recognised by the machine. */
export function ServiceChips({ codes }: { codes: readonly string[] }) {
  if (codes.length === 0) return <span className="text-small text-ink-soft">Tự nhận diện</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {codes.map((code) => (
        <Chip key={code}>{code}</Chip>
      ))}
    </span>
  );
}
