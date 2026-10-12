/** "Đoạn": the chunks of a source, searchable and paged, with the service and kind labels editable per chunk. */
import { useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import { ui } from "../sdk";
import type { Chunk, ChunkList, Service } from "../types";
import { ChunkCard } from "./chunk-card";
import { pageCountOf } from "./detail-logic";

const SEARCH_DELAY_MS = 300;

type Load = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; list: ChunkList };

export function ChunksTab({ sourceId, contentKey }: { sourceId: string; contentKey: string }) {
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [catalog, setCatalog] = useState<Service[]>([]);
  const [catalogError, setCatalogError] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(typed.trim());
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [typed]);

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

  useEffect(() => {
    let stale = false;
    knowledge.chunks(sourceId, { q: query, page }).then(
      (list) => !stale && setLoad({ kind: "ready", list }),
      (err: unknown) => !stale && setLoad({ kind: "error", message: messageOf(err) }),
    );
    return () => {
      stale = true;
    };
  }, [sourceId, contentKey, query, page, attempt]);

  function replaceChunk(next: Chunk) {
    setLoad((current) =>
      current.kind === "ready"
        ? { kind: "ready", list: { ...current.list, items: current.list.items.map((item) => (item.id === next.id ? next : item)) } }
        : current,
    );
  }

  return (
    <div className="space-y-4">
      <ui.Input
        type="search"
        aria-label="Tìm trong các đoạn"
        placeholder="Tìm trong các đoạn (tiêu đề, nội dung)..."
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
      />
      {catalogError && <ui.Notice tone="warning">Không tải được danh mục dịch vụ: chưa sửa được nhãn dịch vụ.</ui.Notice>}
      <ChunkBody
        load={load}
        catalog={catalog}
        searching={query !== ""}
        onChanged={replaceChunk}
        onRetry={() => {
          setLoad({ kind: "loading" });
          setAttempt(attempt + 1);
        }}
      />
      {load.kind === "ready" && <Pager list={load.list} onPage={setPage} />}
    </div>
  );
}

function ChunkBody({
  load,
  catalog,
  searching,
  onChanged,
  onRetry,
}: {
  load: Load;
  catalog: readonly Service[];
  searching: boolean;
  onChanged: (chunk: Chunk) => void;
  onRetry: () => void;
}) {
  if (load.kind === "loading") return <ui.Empty>Đang tải các đoạn...</ui.Empty>;
  if (load.kind === "error") {
    return (
      <div className="space-y-3">
        <ui.Notice tone="danger">{load.message}</ui.Notice>
        <ui.Button variant="secondary" onClick={onRetry}>
          Thử lại
        </ui.Button>
      </div>
    );
  }
  if (load.list.items.length === 0) {
    return <ui.Empty>{searching ? "Không có đoạn nào khớp." : "Nguồn này chưa có đoạn nào (chưa nạp xong hoặc bị lỗi)."}</ui.Empty>;
  }
  return (
    <ul className="space-y-3">
      {load.list.items.map((chunk) => (
        <li key={chunk.id}>
          <ChunkCard chunk={chunk} catalog={catalog} onChanged={onChanged} />
        </li>
      ))}
    </ul>
  );
}

function Pager({ list, onPage }: { list: ChunkList; onPage: (page: number) => void }) {
  const pages = pageCountOf(list.total, list.page_size);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-small text-ink-soft">{list.total} đoạn</span>
      <div className="flex items-center gap-2">
        <ui.Button variant="secondary" disabled={list.page <= 1} onClick={() => onPage(list.page - 1)}>
          Trước
        </ui.Button>
        <span className="text-small text-ink-soft">
          Trang {list.page}/{pages}
        </span>
        <ui.Button variant="secondary" disabled={list.page >= pages} onClick={() => onPage(list.page + 1)}>
          Sau
        </ui.Button>
      </div>
    </div>
  );
}
