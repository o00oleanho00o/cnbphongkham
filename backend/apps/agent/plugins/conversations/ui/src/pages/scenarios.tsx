/** "Kịch bản": what customers asked and how the staff reacted, cut from the kept conversations with personal
 * details hidden; the agent is shown the closest ones before it answers. Try a question, switch one off, delete one. */
import { useCallback, useEffect, useState } from "react";

import { messageOf, scenarios } from "../client";
import { formatTime } from "../logic";
import { ui } from "../sdk";
import type { Scenario, ScenarioHit, ScenarioStatus } from "../types";

const PAGE = 30;
const LINE_LABEL = { customer: "Khách", staff: "Nhân viên" } as const;
const HOW_LABEL = { meaning: "Theo nghĩa", words: "Theo từ khóa" } as const;

function Transcript({ scenario }: { scenario: Scenario }) {
  return (
    <div className="space-y-2">
      {scenario.transcript.map((line, index) => (
        <div key={`${index}-${line.role}`} className={`flex ${line.role === "customer" ? "justify-start" : "justify-end"}`}>
          <p
            className={`max-w-[85%] rounded-tile px-3 py-2 text-small whitespace-pre-wrap ${
              line.role === "customer" ? "bg-tile text-heading" : "bg-brand-500/10 text-heading"
            }`}
          >
            <span className="mr-1 font-bold">{LINE_LABEL[line.role]}:</span>
            {line.text}
          </p>
        </div>
      ))}
    </div>
  );
}

function Card({
  scenario,
  note,
  onChange,
  onRemoved,
}: {
  scenario: Scenario;
  note?: string;
  onChange: (next: Scenario) => void;
  onRemoved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function toggle(enabled: boolean) {
    setBusy(true);
    setError("");
    try {
      onChange(await scenarios.enable(scenario.id, enabled));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await scenarios.remove(scenario.id);
      onRemoved();
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-tile border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="text-body font-bold break-words text-heading">{scenario.ask}</p>
          <p className="flex flex-wrap items-center gap-2">
            <ui.Badge tone="info">{scenario.channel}</ui.Badge>
            <ui.Badge tone={scenario.repeats > 1 ? "success" : "neutral"}>
              {scenario.repeats > 1 ? `Đã gặp ${scenario.repeats} lần` : "Gặp 1 lần"}
            </ui.Badge>
            {!scenario.enabled && <ui.Badge tone="warning">Đang tắt</ui.Badge>}
            {note && <ui.Badge>{note}</ui.Badge>}
            <span className="text-label text-ink-soft">{formatTime(scenario.updated_at)}</span>
          </p>
        </div>
        <ui.Toggle
          checked={scenario.enabled}
          label={`Cho trợ lý dùng kịch bản: ${scenario.ask}`}
          disabled={busy}
          onChange={(enabled) => void toggle(enabled)}
        />
      </div>
      {open && <Transcript scenario={scenario} />}
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <div className="flex flex-wrap items-center gap-2">
        <ui.Button variant="secondary" onClick={() => setOpen((shown) => !shown)}>
          {open ? "Ẩn hội thoại" : "Xem hội thoại"}
        </ui.Button>
        {asking ? (
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-small text-ink-soft">Xóa kịch bản này?</span>
            <ui.Button variant="danger" busy={busy} onClick={() => void remove()}>
              Xóa
            </ui.Button>
            <ui.Button variant="ghost" onClick={() => setAsking(false)}>
              Hủy
            </ui.Button>
          </span>
        ) : (
          <ui.Button variant="ghost" disabled={busy} onClick={() => setAsking(true)}>
            Xóa
          </ui.Button>
        )}
      </div>
    </li>
  );
}

function Status({ status, onRefresh, busy }: { status: ScenarioStatus | null; onRefresh: () => void; busy: boolean }) {
  if (status === null) return null;
  const how = status.embedding_connected
    ? "Đang tìm theo nghĩa (embedding đã kết nối)."
    : "Đang tìm bằng từ khóa: embedding chưa kết nối ở Kho tri thức.";
  return (
    <ui.Card
      title="Tình trạng"
      aside={
        <ui.Button variant="secondary" busy={busy} onClick={onRefresh}>
          Cập nhật ngay
        </ui.Button>
      }
    >
      <div className="space-y-1 text-small text-ink">
        <p>
          {status.scenarios} kịch bản
          {status.embedding_connected && status.without_vector > 0 ? `, ${status.without_vector} đang chờ nhúng` : ""}.
        </p>
        <p className="text-ink-soft">{how}</p>
        {status.embedding_error && <p className="text-danger">{status.embedding_error}</p>}
        <p className="text-ink-soft">
          Kịch bản được cắt từ cuộc trò chuyện đã im 30 phút, chỉ giữ những đoạn có nhân viên trả lời, đã che tên, số
          điện thoại, địa chỉ. Cập nhật ngay cắt cả những cuộc đang nhắn.
        </p>
      </div>
    </ui.Card>
  );
}

function TrySearch({ channels }: { channels: readonly string[] }) {
  const [question, setQuestion] = useState("");
  const [channel, setChannel] = useState("");
  const [hits, setHits] = useState<ScenarioHit[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const options = [{ value: "", label: "Không chọn kênh" }, ...channels.map((name) => ({ value: name, label: name }))];

  async function run() {
    setBusy(true);
    setError("");
    try {
      setHits((await scenarios.search(question.trim(), channel)).hits);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ui.Card title="Thử tìm">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <p className="text-small text-ink-soft">
          Gõ một câu khách có thể hỏi và chọn kênh sẽ trả lời: xem trợ lý sẽ được cho xem những kịch bản nào.
        </p>
        <div className="flex flex-wrap gap-2">
          <div className="min-w-48 flex-1">
            <ui.Input
              aria-label="Câu khách hỏi"
              placeholder="Ví dụ: giá điều trị nám bao nhiêu"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </div>
          <ui.Select
            aria-label="Kênh trả lời"
            value={channel}
            options={options}
            onChange={(event) => setChannel(event.target.value)}
          />
          <ui.Button type="submit" busy={busy} disabled={question.trim().length < 3}>
            Thử
          </ui.Button>
        </div>
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
        {hits !== null && hits.length === 0 && !error && (
          <ui.Empty>Không có kịch bản nào đủ giống (theo phạm vi và độ giống ở tab Cài đặt).</ui.Empty>
        )}
        <ul className="space-y-2">
          {(hits ?? []).map((hit) => (
            <Card
              key={hit.id}
              scenario={hit}
              note={`${HOW_LABEL[hit.how]} · ${hit.score}`}
              onChange={() => undefined}
              onRemoved={() => setHits((before) => (before ?? []).filter((other) => other.id !== hit.id))}
            />
          ))}
        </ul>
      </form>
    </ui.Card>
  );
}

export function ScenariosPage({ channels }: { channels: readonly string[] }) {
  const [rows, setRows] = useState<Scenario[] | null>(null);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<ScenarioStatus | null>(null);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState("");
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [found, state] = await Promise.all([
        scenarios.list({ channel, q: search, limit: PAGE, offset: 0 }),
        scenarios.status(),
      ]);
      setRows(found.scenarios);
      setTotal(found.total);
      setStatus(state);
    } catch (err) {
      setError(messageOf(err));
      setRows([]);
    }
  }, [channel, search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      await scenarios.refresh();
      await load();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setRefreshing(false);
    }
  }

  async function more() {
    setLoadingMore(true);
    try {
      const found = await scenarios.list({ channel, q: search, limit: PAGE, offset: rows?.length ?? 0 });
      setRows((before) => [...(before ?? []), ...found.scenarios]);
      setTotal(found.total);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoadingMore(false);
    }
  }

  const options = [{ value: "", label: "Mọi kênh" }, ...channels.map((name) => ({ value: name, label: name }))];

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Kịch bản mẫu"
        subtitle="Cách nhân viên đã phản ứng khi khách hỏi. Trợ lý được xem những kịch bản gần giống trước khi trả lời, để học bước đi và giọng điệu, không chép số liệu."
      />
      <Status status={status} onRefresh={() => void refresh()} busy={refreshing} />
      <TrySearch channels={channels} />
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(typed.trim());
        }}
      >
        <div className="min-w-48 flex-1">
          <ui.Input
            aria-label="Tìm trong kịch bản"
            placeholder="Tìm trong kịch bản"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        <ui.Select
          aria-label="Lọc theo kênh"
          value={channel}
          options={options}
          onChange={(event) => setChannel(event.target.value)}
        />
        <ui.Button type="submit" variant="secondary">
          Tìm
        </ui.Button>
      </form>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {rows === null && <p className="py-6 text-center text-small text-ink-soft">Đang tải…</p>}
      {rows !== null && rows.length === 0 && !error && (
        <ui.Card>
          <p className="text-center text-body font-bold text-heading">Chưa có kịch bản nào</p>
          <ui.Empty>
            Kịch bản xuất hiện khi một cuộc trò chuyện đã lưu có khách hỏi và nhân viên trả lời. Bật lưu hội thoại ở tab
            Cài đặt trước.
          </ui.Empty>
        </ui.Card>
      )}
      <ul className="space-y-2">
        {(rows ?? []).map((scenario) => (
          <Card
            key={scenario.id}
            scenario={scenario}
            onChange={(next) => setRows((before) => (before ?? []).map((row) => (row.id === next.id ? next : row)))}
            onRemoved={() => void load()}
          />
        ))}
      </ul>
      {rows !== null && rows.length < total && (
        <div className="flex justify-center">
          <ui.Button variant="secondary" busy={loadingMore} onClick={() => void more()}>
            {`Xem thêm (${total - rows.length})`}
          </ui.Button>
        </div>
      )}
    </div>
  );
}
