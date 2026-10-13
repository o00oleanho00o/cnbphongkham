/** "Danh sách": every skill, rules and persona item, who wrote it, where it applies; add one or open one. */
import { useCallback, useEffect, useMemo, useState } from "react";

import { messageOf, skills } from "../client";
import { ItemSheet } from "../form/item-sheet";
import {
  KINDS,
  KIND_LABEL,
  ORIGIN_LABEL,
  STATUSES,
  STATUS_LABEL,
  STATUS_TONE,
  filterItems,
  formatTime,
  scopeLabel,
} from "../logic";
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { Choices, Item, Kind, Status } from "../types";

const KIND_FILTER = [{ value: "", label: "Mọi loại" }, ...KINDS.map((kind) => ({ value: kind.id, label: kind.label }))];
const STATUS_FILTER = [{ value: "", label: "Mọi trạng thái" }, ...STATUSES.map((s) => ({ value: s.id, label: s.label }))];

function asKind(value: string): Kind | "" {
  return KINDS.find((kind) => kind.id === value)?.id ?? "";
}

function asStatus(value: string): Status | "" {
  return STATUSES.find((status) => status.id === value)?.id ?? "";
}

function Row({ item, onOpen }: { item: Item; onOpen: () => void }) {
  const scopes = item.scopes.length === 0 ? ["agent"] : item.scopes;
  return (
    <li className="space-y-2 rounded-tile border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-body font-bold break-all text-heading">{item.name}</span>
            <ui.Badge>{KIND_LABEL[item.kind]}</ui.Badge>
            <ui.Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</ui.Badge>
          </p>
          <p className="text-body text-ink">{item.description}</p>
        </div>
        <ui.Button variant="secondary" onClick={onOpen}>
          Mở
        </ui.Button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {scopes.map((scope) => (
          <Chip key={scope}>{scopeLabel(scope)}</Chip>
        ))}
      </div>
      <p className="text-label text-ink-soft">
        Phiên bản {item.version} · {ORIGIN_LABEL[item.origin]} · {item.updated_by} · {formatTime(item.updated_at)}
      </p>
    </li>
  );
}

export function ListPage({ choices }: { choices: Choices }) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<Kind | "">("");
  const [status, setStatus] = useState<Status | "">("");
  const [open, setOpen] = useState<Item | "new" | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      setItems((await skills.items()).items);
    } catch (err) {
      setError(messageOf(err));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => filterItems(items ?? [], q, kind, status), [items, q, kind, status]);

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Kỹ năng, quy tắc và giọng điệu"
        subtitle="Nội dung agent đọc ở mỗi cuộc trò chuyện. Chọn nơi áp dụng: cả agent, một plugin (Zalo) hay một tài khoản."
        aside={<ui.Button onClick={() => setOpen("new")}>Thêm mới</ui.Button>}
      />
      <div className="flex flex-wrap gap-2">
        <div className="min-w-48 flex-1">
          <ui.Input
            aria-label="Tìm theo tên hoặc mô tả"
            placeholder="Tìm theo tên hoặc mô tả"
            value={q}
            onChange={(event) => setQ(event.target.value)}
          />
        </div>
        <ui.Select
          aria-label="Lọc theo loại"
          value={kind}
          options={KIND_FILTER}
          onChange={(event) => setKind(asKind(event.target.value))}
        />
        <ui.Select
          aria-label="Lọc theo trạng thái"
          value={status}
          options={STATUS_FILTER}
          onChange={(event) => setStatus(asStatus(event.target.value))}
        />
      </div>
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
      {items === null && <p className="py-6 text-center text-small text-ink-soft">Đang tải…</p>}
      {items !== null && items.length === 0 && !error && (
        <ui.Card>
          <p className="text-center text-body font-bold text-heading">Chưa có mục nào</p>
          <ui.Empty>Thêm một kỹ năng, một quy tắc hoặc một giọng điệu để agent dùng.</ui.Empty>
        </ui.Card>
      )}
      {items !== null && items.length > 0 && shown.length === 0 && <ui.Empty>Không có mục nào khớp bộ lọc.</ui.Empty>}
      <ul className="space-y-2">
        {shown.map((item) => (
          <Row key={item.id} item={item} onOpen={() => setOpen(item)} />
        ))}
      </ul>
      {open !== null && (
        <ItemSheet
          key={open === "new" ? "new" : open.id}
          item={open === "new" ? null : open}
          choices={choices}
          onClose={() => setOpen(null)}
          onSaved={() => void load()}
        />
      )}
    </div>
  );
}
