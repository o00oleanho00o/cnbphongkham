/** The filter row above the table: search, processing, audience, service, lifecycle and "not approved". */
import { useEffect, useState } from "react";

import { APPROVAL_STEP, AUDIENCE_LABEL, LIFECYCLE_LABEL, PROCESSING_LABEL } from "../logic";
import { ui } from "../sdk";
import type { Service } from "../types";
import { type Filters, NO_FILTERS, hasFilters } from "./sources-logic";

const DEBOUNCE_MS = 300;

function optionsOf(all: string, labels: Record<string, string>) {
  return [{ value: "", label: all }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))];
}

export function SourceFilters({
  filters,
  services,
  onChange,
}: {
  filters: Filters;
  services: readonly Service[];
  onChange: (next: Filters) => void;
}) {
  const [text, setText] = useState(filters.q);

  // Typing waits a moment before it reloads the list; a reset from outside refills the box.
  useEffect(() => {
    if (text === filters.q) return;
    const timer = setTimeout(() => onChange({ ...filters, q: text }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, filters, onChange]);
  useEffect(() => setText(filters.q), [filters.q]);

  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const serviceOptions = [
    { value: "", label: "Mọi dịch vụ" },
    ...services.map((service) => ({ value: service.code, label: service.name })),
  ];

  return (
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
      <div className="sm:col-span-2 lg:col-span-2">
        <ui.Input
          type="search"
          aria-label="Tìm theo tên hoặc mã tài liệu"
          placeholder="Tìm theo tên hoặc mã tài liệu"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </div>
      <ui.Select
        aria-label="Trạng thái xử lý"
        value={filters.processing}
        options={optionsOf("Mọi trạng thái", PROCESSING_LABEL)}
        onChange={(event) => set({ processing: event.target.value })}
      />
      <ui.Select
        aria-label="Đối tượng"
        value={filters.audience}
        options={optionsOf("Mọi đối tượng", AUDIENCE_LABEL)}
        onChange={(event) => set({ audience: event.target.value })}
      />
      <ui.Select
        aria-label="Dịch vụ"
        value={filters.service}
        options={serviceOptions}
        onChange={(event) => set({ service: event.target.value })}
      />
      <ui.Select
        aria-label="Hiệu lực"
        value={filters.lifecycle}
        options={optionsOf("Mọi hiệu lực", LIFECYCLE_LABEL)}
        onChange={(event) => set({ lifecycle: event.target.value })}
      />
      {APPROVAL_STEP && (
        <label className="flex min-h-11 items-center gap-2 text-small text-ink sm:min-h-0">
          <input
            type="checkbox"
            checked={filters.unapproved}
            onChange={(event) => set({ unapproved: event.target.checked })}
            className="size-5 accent-brand-500 sm:size-4"
          />
          Chưa duyệt
        </label>
      )}
      {hasFilters(filters) && (
        <div className="sm:col-span-2 lg:col-span-1">
          <ui.Button variant="ghost" onClick={() => onChange(NO_FILTERS)}>
            Xóa bộ lọc
          </ui.Button>
        </div>
      )}
    </div>
  );
}
