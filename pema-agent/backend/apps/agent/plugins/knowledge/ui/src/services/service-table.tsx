/** The catalogue: a table on a wide screen, cards on a phone. Aliases and the on/off switch save at once. */
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { Service } from "../types";
import { WordEditor } from "./word-editor";

export interface RowActions {
  /** Id of the service being saved (its controls wait). */
  busyId: string;
  onAliases: (service: Service, aliases: string[]) => void;
  onEnabled: (service: Service, enabled: boolean) => void;
  onEdit: (service: Service) => void;
  onDelete: (service: Service) => void;
}

function Branches({ branches }: { branches: readonly string[] }) {
  if (branches.length === 0) return <span className="text-label text-ink-soft">Mọi chi nhánh</span>;
  return (
    <span className="flex flex-wrap gap-1.5">
      {branches.map((branch) => (
        <Chip key={branch}>{branch}</Chip>
      ))}
    </span>
  );
}

function Aliases({ service, actions }: { service: Service; actions: RowActions }) {
  return (
    <WordEditor
      label={`Tên gọi khác của ${service.name}`}
      words={service.aliases}
      placeholder="Thêm tên gọi khác, Enter"
      disabled={actions.busyId === service.id}
      onChange={(next) => actions.onAliases(service, next)}
    />
  );
}

function EnabledToggle({ service, actions }: { service: Service; actions: RowActions }) {
  return (
    <ui.Toggle
      checked={service.enabled}
      label={`Bật ${service.name}`}
      disabled={actions.busyId === service.id}
      onChange={(next) => actions.onEnabled(service, next)}
    />
  );
}

function RowButtons({ service, actions }: { service: Service; actions: RowActions }) {
  return (
    <div className="flex flex-wrap gap-1">
      <ui.Button variant="ghost" aria-label={`Sửa ${service.name}`} onClick={() => actions.onEdit(service)}>
        Sửa
      </ui.Button>
      <ui.Button variant="ghost" aria-label={`Xóa ${service.name}`} onClick={() => actions.onDelete(service)}>
        Xóa
      </ui.Button>
    </div>
  );
}

function ServiceCard({ service, actions }: { service: Service; actions: RowActions }) {
  return (
    <li className="space-y-3 rounded-tile border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-label font-semibold text-ink-soft">{service.code}</p>
          <p className="font-semibold break-words text-ink">{service.name}</p>
        </div>
        <EnabledToggle service={service} actions={actions} />
      </div>
      {service.description && <p className="text-small text-ink-soft">{service.description}</p>}
      <Aliases service={service} actions={actions} />
      <Branches branches={service.branches} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-label text-ink-soft">{`${service.chunk_count} đoạn đang gắn`}</span>
        <RowButtons service={service} actions={actions} />
      </div>
    </li>
  );
}

const HEADERS = ["Mã", "Tên", "Tên gọi khác", "Mô tả", "Chi nhánh", "Đoạn", "Bật", ""] as const;

export function ServiceTable({ services, actions }: { services: readonly Service[]; actions: RowActions }) {
  return (
    <>
      <ul className="space-y-3 md:hidden">
        {services.map((service) => (
          <ServiceCard key={service.id} service={service} actions={actions} />
        ))}
      </ul>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-small">
          <thead>
            <tr className="border-b border-line text-label text-ink-soft">
              {HEADERS.map((header, index) => (
                <th key={header || index} scope="col" className="px-2 py-2 font-medium">
                  {header || <span className="sr-only">Thao tác</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line align-top">
            {services.map((service) => (
              <tr key={service.id}>
                <td className="px-2 py-3 font-mono font-semibold text-ink">{service.code}</td>
                <td className="px-2 py-3 text-ink">{service.name}</td>
                <td className="min-w-56 px-2 py-3">
                  <Aliases service={service} actions={actions} />
                </td>
                <td className="px-2 py-3 text-ink-soft">{service.description}</td>
                <td className="px-2 py-3">
                  <Branches branches={service.branches} />
                </td>
                <td className="px-2 py-3 text-ink">{service.chunk_count}</td>
                <td className="px-2 py-2">
                  <EnabledToggle service={service} actions={actions} />
                </td>
                <td className="px-2 py-2">
                  <RowButtons service={service} actions={actions} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
