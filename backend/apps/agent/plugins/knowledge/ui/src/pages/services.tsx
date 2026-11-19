/** Dịch vụ: the backbone of the labels. Names, other names (aliases), branches, how many chunks carry each code. */
import { useCallback, useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import { ImportSheet } from "../services/import-sheet";
import { ServiceSheet } from "../services/service-form";
import { INTRO_TEXT, deleteWarning, matchesQuery } from "../services/services-logic";
import { ServiceTable } from "../services/service-table";
import type { Service, ServiceBody } from "../types";

/** `"new"` while adding, the service while changing it, null when the sheet is closed. */
type Editing = "new" | Service | null;

function writeService(editing: Editing, body: ServiceBody): Promise<Service> {
  if (editing === null || editing === "new") return knowledge.createService(body);
  return knowledge.updateService(editing.id, body);
}

export function ServicesPage() {
  const [services, setServices] = useState<Service[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<Service | null>(null);
  const [importing, setImporting] = useState(false);
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setServices(await knowledge.services());
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (saved: Service) =>
    setServices((before) => before?.map((service) => (service.id === saved.id ? saved : service)) ?? null);

  async function patch(service: Service, body: Partial<ServiceBody>) {
    setBusyId(service.id);
    setNotice("");
    try {
      replace(await knowledge.updateService(service.id, body));
      setError("");
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusyId("");
    }
  }

  async function save(body: ServiceBody) {
    const adding = editing === "new";
    await writeService(editing, body);
    setNotice(adding ? `Đã thêm dịch vụ ${body.name}.` : `Đã lưu dịch vụ ${body.name}.`);
    setEditing(null);
    await load();
  }

  async function remove(service: Service) {
    setDeleting(null);
    try {
      await knowledge.deleteService(service.id);
      setNotice(`Đã xóa dịch vụ ${service.name}.`);
      await load();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  function imported(summary: string) {
    setImporting(false);
    setNotice(summary);
    void load();
  }

  const shown = (services ?? []).filter((service) => matchesQuery(service, query));

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Dịch vụ"
        subtitle={INTRO_TEXT}
        aside={
          <div className="flex flex-wrap gap-2">
            <ui.Button variant="secondary" onClick={() => setImporting(true)}>
              Nhập từ bảng
            </ui.Button>
            <ui.Button onClick={() => setEditing("new")}>+ Thêm dịch vụ</ui.Button>
          </div>
        }
      />
      {notice && <ui.Notice tone="success">{notice}</ui.Notice>}
      {error && (
        <ui.Notice tone="danger">
          <span className="flex flex-wrap items-center justify-between gap-2">
            {error}
            <ui.Button variant="secondary" onClick={() => void load()}>
              Thử lại
            </ui.Button>
          </span>
        </ui.Notice>
      )}
      <ui.Card
        aside={
          <div className="w-full sm:w-72">
            <ui.Input
              type="search"
              aria-label="Tìm dịch vụ"
              value={query}
              placeholder="Tìm theo mã, tên, tên gọi khác"
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        }
      >
        {services === null && !error && <ui.Empty>Đang tải…</ui.Empty>}
        {services?.length === 0 && <ui.Empty>Chưa có dịch vụ nào. Bấm "+ Thêm dịch vụ" hoặc "Nhập từ bảng".</ui.Empty>}
        {services && services.length > 0 && shown.length === 0 && <ui.Empty>Không có dịch vụ nào khớp "{query}".</ui.Empty>}
        {shown.length > 0 && (
          <ServiceTable
            services={shown}
            actions={{
              busyId,
              onAliases: (service, aliases) => void patch(service, { aliases }),
              onEnabled: (service, enabled) => void patch(service, { enabled }),
              onEdit: setEditing,
              onDelete: setDeleting,
            }}
          />
        )}
      </ui.Card>
      {editing && (
        <ServiceSheet
          service={editing === "new" ? null : editing}
          services={services ?? []}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
      {importing && <ImportSheet existing={services ?? []} onClose={() => setImporting(false)} onDone={imported} />}
      {deleting && (
        <ConfirmDialog
          title={`Xóa dịch vụ ${deleting.name}?`}
          onClose={() => setDeleting(null)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setDeleting(null)}>
                Giữ lại
              </ui.Button>
              <ui.Button variant="danger" onClick={() => void remove(deleting)}>
                Xóa dịch vụ
              </ui.Button>
            </>
          }
        >
          {deleteWarning(deleting)}
        </ConfirmDialog>
      )}
    </div>
  );
}
