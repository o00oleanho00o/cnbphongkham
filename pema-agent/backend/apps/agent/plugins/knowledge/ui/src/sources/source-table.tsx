/** The sources as a table on a wide screen and as cards on a phone. */
import type { ReactNode } from "react";

import type { Source } from "../types";
import {
  ApprovalCell,
  AudienceCell,
  KindCell,
  LifecycleCell,
  ProcessingCell,
  ServicesCell,
  TitleCell,
  UpdatedCell,
} from "./source-cells";
import { allSelected } from "./sources-logic";
import { APPROVAL_STEP, AUDIENCE_SPLIT } from "../logic";

interface Props {
  items: readonly Source[];
  selected: readonly string[];
  serviceNames: ReadonlyMap<string, string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onOpen: (id: string) => void;
}

const HEADERS = ["Tên", "Loại", "Dịch vụ", ...(AUDIENCE_SPLIT ? ["Đối tượng"] : []), "Trạng thái xử lý", "Hiệu lực", ...(APPROVAL_STEP ? ["Duyệt"] : []), "Đoạn", "Cập nhật"];

function PickBox({ checked, label, onChange }: { checked: boolean; label: string; onChange: () => void }) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={checked}
      onChange={onChange}
      className="size-5 shrink-0 accent-brand-500 sm:size-4"
    />
  );
}

function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-0.5 text-micro text-ink-soft">{label}</p>
      {children}
    </div>
  );
}

export function SourceTable({ items, selected, serviceNames, onToggle, onToggleAll, onOpen }: Props) {
  const pageSelected = allSelected(
    selected,
    items.map((item) => item.id),
  );
  return (
    <>
      <div className="hidden overflow-x-auto rounded-card border border-line bg-surface shadow-card lg:block">
        <table className="w-full min-w-[960px] text-left text-small">
          <thead className="border-b border-line bg-tile text-label text-ink-soft">
            <tr>
              <th scope="col" className="w-10 px-3 py-2">
                <PickBox checked={pageSelected} label="Chọn tất cả nguồn trong trang" onChange={onToggleAll} />
              </th>
              {HEADERS.map((header) => (
                <th key={header} scope="col" className="px-3 py-2 font-medium">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((source) => (
              <tr key={source.id} className="border-b border-line align-top last:border-b-0">
                <td className="px-3 py-3">
                  <PickBox
                    checked={selected.includes(source.id)}
                    label={`Chọn ${source.title}`}
                    onChange={() => onToggle(source.id)}
                  />
                </td>
                <td className="max-w-64 px-3 py-3">
                  <TitleCell source={source} onOpen={() => onOpen(source.id)} />
                </td>
                <td className="px-3 py-3">
                  <KindCell source={source} />
                </td>
                <td className="max-w-44 px-3 py-3">
                  <ServicesCell source={source} names={serviceNames} />
                </td>
                {AUDIENCE_SPLIT && (
                  <td className="px-3 py-3">
                    <AudienceCell source={source} />
                  </td>
                )}
                <td className="max-w-56 px-3 py-3">
                  <ProcessingCell source={source} />
                </td>
                <td className="px-3 py-3">
                  <LifecycleCell source={source} />
                </td>
                {APPROVAL_STEP && (
                  <td className="px-3 py-3">
                    <ApprovalCell source={source} />
                  </td>
                )}
                <td className="px-3 py-3 text-ink">{source.chunk_count}</td>
                <td className="px-3 py-3">
                  <UpdatedCell source={source} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 lg:hidden">
        <li className="flex items-center gap-3 px-1">
          <PickBox checked={pageSelected} label="Chọn tất cả nguồn trong trang" onChange={onToggleAll} />
          <span className="text-small text-ink-soft">Chọn tất cả trong trang</span>
        </li>
        {items.map((source) => (
          <li key={source.id} className="space-y-3 rounded-card border border-line bg-surface p-4 shadow-card">
            <div className="flex items-start gap-3">
              <PickBox
                checked={selected.includes(source.id)}
                label={`Chọn ${source.title}`}
                onChange={() => onToggle(source.id)}
              />
              <TitleCell source={source} onOpen={() => onOpen(source.id)} />
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Labelled label="Loại">
                <KindCell source={source} />
              </Labelled>
              {AUDIENCE_SPLIT && (
                <Labelled label="Đối tượng">
                  <AudienceCell source={source} />
                </Labelled>
              )}
              <Labelled label="Hiệu lực">
                <LifecycleCell source={source} />
              </Labelled>
              {APPROVAL_STEP && (
                <Labelled label="Duyệt">
                  <ApprovalCell source={source} />
                </Labelled>
              )}
            </div>
            <Labelled label="Dịch vụ">
              <ServicesCell source={source} names={serviceNames} />
            </Labelled>
            <Labelled label="Trạng thái xử lý">
              <ProcessingCell source={source} />
            </Labelled>
            <p className="text-micro text-ink-soft">
              {source.chunk_count} đoạn · cập nhật <UpdatedCell source={source} />
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
