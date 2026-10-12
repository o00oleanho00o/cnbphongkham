/** "Nguồn": the documents the agent can look up, with their state, filters and bulk actions. */
import { useCallback, useEffect, useMemo, useState } from "react";

import { AddSourceSheet } from "../add/add-source";
import { knowledge, messageOf } from "../client";
import { Stat } from "../parts";
import { ui } from "../sdk";
import { BulkBar } from "../sources/bulk-bar";
import { SourceFilters } from "../sources/source-filters";
import { SourceTable } from "../sources/source-table";
import {
  type BulkKind,
  type Filters,
  NO_FILTERS,
  bulkActionOf,
  bulkDoneText,
  failureLines,
  hasFilters,
  pageCount,
  pruneSelection,
  rangeText,
  toQuery,
  toggleAll,
  toggleId,
  visibleWarnings,
} from "../sources/sources-logic";
import { useSourceList } from "../sources/use-source-list";
import type { Service } from "../types";
import { SourceDetail } from "./source-detail";
import { useStoreNav } from "./store";

const NOTICE_MS = 5000;

function useServices(): Service[] {
  const [services, setServices] = useState<Service[]>([]);
  useEffect(() => {
    knowledge
      .services()
      .then(setServices)
      .catch(() => setServices([]));
  }, []);
  return services;
}

export function SourcesPage() {
  const nav = useStoreNav();
  const { focus, clearFocus } = nav;
  const [openId, setOpenId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const [failures, setFailures] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const services = useServices();
  const { list, error, loading, reload } = useSourceList(toQuery(filters, page));
  const serviceNames = useMemo(() => new Map(services.map((service) => [service.code, service.name])), [services]);

  // A link from another tab (or a history row) opens that source once.
  useEffect(() => {
    if (!focus.source) return;
    setOpenId(focus.source);
    clearFocus();
  }, [focus.source, clearFocus]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const items = list?.items;
  useEffect(() => {
    if (!items) return;
    setSelected((current) =>
      pruneSelection(
        current,
        items.map((item) => item.id),
      ),
    );
  }, [items]);

  const pages = list ? pageCount(list.total, list.page_size) : 1;
  useEffect(() => {
    if (list && page > pages) setPage(pages);
  }, [list, page, pages]);

  const changeFilters = useCallback((next: Filters) => {
    setFilters(next);
    setPage(1);
  }, []);

  async function runBulk(kind: BulkKind) {
    if (!items) return;
    setBusy(true);
    setActionError("");
    setFailures([]);
    try {
      const result = await knowledge.bulk(selected, bulkActionOf(kind));
      setNotice(bulkDoneText(kind, result.done));
      setFailures(failureLines(result, items));
      setSelected(result.failed.map((row) => row.id));
      await reload(true);
    } catch (err) {
      setActionError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function added(count: number) {
    setAdding(false);
    setNotice(`Đã thêm ${count} nguồn`);
    void reload(true);
  }

  function backToList() {
    setOpenId(null);
    void reload(true);
  }

  if (openId) return <SourceDetail id={openId} onBack={backToList} />;

  const noSourcesAtAll = list !== null && list.total === 0 && !hasFilters(filters);
  const picked = (items ?? []).filter((item) => selected.includes(item.id));

  return (
    <div>
      <ui.PageHeader
        title="Nguồn"
        subtitle="Tài liệu agent tra cứu để trả lời"
        aside={<ui.Button onClick={() => setAdding(true)}>+ Thêm nguồn</ui.Button>}
      />
      {notice && <div className="mb-4"><ui.Notice tone="success">{notice}</ui.Notice></div>}
      {actionError && <div className="mb-4"><ui.Notice tone="danger">{actionError}</ui.Notice></div>}
      {failures.length > 0 && (
        <div className="mb-4">
          <ui.Notice tone="warning">
            <p className="font-medium">Không làm được với {failures.length} nguồn:</p>
            <ul className="list-disc pl-5">
              {failures.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </ui.Notice>
        </div>
      )}

      {error && (
        <div className="mb-4 space-y-2">
          <ui.Notice tone="danger">{error}</ui.Notice>
          <ui.Button variant="secondary" onClick={() => void reload()}>
            Thử lại
          </ui.Button>
        </div>
      )}
      {!list && loading && <ui.Empty>Đang tải danh sách nguồn…</ui.Empty>}

      {list && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Nguồn sẵn sàng" value={list.summary.ready} />
            <Stat label="Đoạn" value={list.summary.chunks} />
            <Stat label="Đã nhúng vector" value={`${list.summary.embedded_percent}%`} />
            <Stat label="Lỗi" value={list.summary.errors} tone={list.summary.errors > 0 ? "danger" : "neutral"} />
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {visibleWarnings(list.warnings).map((text) => (
              <ui.Notice key={text} tone="warning">
                {text}
              </ui.Notice>
            ))}
            {list.summary.unapproved > 0 && (
              <ui.Button
                variant="secondary"
                aria-pressed={filters.unapproved}
                onClick={() => changeFilters({ ...filters, unapproved: !filters.unapproved })}
              >
                {list.summary.unapproved} nguồn chưa duyệt
                {filters.unapproved ? " (đang lọc)" : ""}
              </ui.Button>
            )}
          </div>
        </>
      )}

      {noSourcesAtAll ? (
        <ui.Card>
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <h2 className="text-section font-bold text-heading">Chưa có nguồn nào</h2>
            <p className="max-w-md text-small text-ink-soft">
              Nguồn là một tài liệu (tệp hoặc văn bản bạn gõ) mà agent đọc, chia nhỏ và tra cứu khi trả lời.
            </p>
            <ui.Button onClick={() => setAdding(true)}>Thêm nguồn</ui.Button>
          </div>
        </ui.Card>
      ) : (
        list && (
          <>
            <SourceFilters filters={filters} services={services} onChange={changeFilters} />
            {picked.length > 0 && (
              <BulkBar picked={picked} busy={busy} onRun={(kind) => void runBulk(kind)} onClear={() => setSelected([])} />
            )}
            {list.items.length === 0 ? (
              <ui.Empty>Không có nguồn nào khớp bộ lọc.</ui.Empty>
            ) : (
              <SourceTable
                items={list.items}
                selected={selected}
                serviceNames={serviceNames}
                onToggle={(id) => setSelected((current) => toggleId(current, id))}
                onToggleAll={() =>
                  setSelected((current) =>
                    toggleAll(
                      current,
                      list.items.map((item) => item.id),
                    ),
                  )
                }
                onOpen={setOpenId}
              />
            )}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-small text-ink-soft">{rangeText(list, list.items.length)}</p>
              {pages > 1 && (
                <div className="flex items-center gap-2">
                  <ui.Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                    Trước
                  </ui.Button>
                  <span className="text-small text-ink">
                    Trang {page} / {pages}
                  </span>
                  <ui.Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                    Sau
                  </ui.Button>
                </div>
              )}
            </div>
          </>
        )
      )}

      {adding && <AddSourceSheet onClose={() => setAdding(false)} onAdded={added} />}
    </div>
  );
}
