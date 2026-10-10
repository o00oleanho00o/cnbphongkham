"use client";

// Trace của agent: one row per turn (the agent's answer to one message): when, channel, model, steps, time, tokens and
// how it ended; a filter on the channel, on the failed ones and on one chat (`?session=`). A row opens the steps of the
// turn (model calls, tool calls, guards, compactions) with their time and errors. Only timings, tokens and outcomes are
// traced; the words of the chat are in "Phiên chat".
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyRow, formatTime, TableShell } from "@/components/admin/shared/ui-bits";
import { Pager } from "@/components/admin/shared/ui-bits";
import { Badge, Notice, PageHeader, Select } from "@/components/agent/plugin-kit";
import {
  detailText,
  errorLabel,
  eventLabel,
  formatCount,
  formatDuration,
  listPath,
  type Paged,
  sessionHref,
  stopLabel,
  totalTokens,
  type TurnDetail,
  type TurnRow,
  TRACES_PATH,
} from "@/lib/agent/activity";
import { agentApi as api } from "@/lib/agent/api";
import { Button, buttonClass } from "@/ui/button";
import { Sheet } from "@/ui/dialog";

const ALL_CHANNELS = "";

export function TracesPage() {
  const params = useSearchParams();
  const session = params.get("session") ?? "";
  const [rows, setRows] = useState<TurnRow[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [channel, setChannel] = useState(ALL_CHANNELS);
  const [channels, setChannels] = useState<string[]>([]);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      const listing = await api.get<Paged<TurnRow>>(
        listPath(TRACES_PATH, { channel, session_id: session, errors_only: errorsOnly, page }),
      );
      setRows(listing.items);
      setHasMore(listing.has_more);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, [channel, session, errorsOnly, page]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    api
      .get<{ channels: { name: string }[] }>("/v1/admin/channels")
      .then((answer) => setChannels(answer.channels.map((c) => c.name)))
      .catch(() => setChannels([]));
  }, []);

  return (
    <div>
      <PageHeader
        title="Trace"
        subtitle="Từng lượt agent trả lời một tin nhắn: model, số bước, thời gian, token và kết cục"
      />
      {error && <Notice tone="danger">{error}</Notice>}
      {session && (
        <div className="mb-3">
          <Notice>
            Chỉ các lượt của phiên <b className="break-all">{session}</b>.{" "}
            <Link href={sessionHref(session)} className="font-medium underline underline-offset-2">
              Xem phiên chat
            </Link>{" "}
            ·{" "}
            <Link href="/admin/agent/traces" className="font-medium underline underline-offset-2">
              Bỏ lọc
            </Link>
          </Notice>
        </div>
      )}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="w-full sm:w-56">
            <Select
              aria-label="Lọc theo kênh"
              value={channel}
              onChange={(e) => {
                setChannel(e.target.value);
                setPage(0);
              }}
              options={[
                { value: ALL_CHANNELS, label: "Mọi kênh" },
                ...channels.map((name) => ({ value: name, label: name })),
              ]}
            />
          </div>
          <label className="flex min-h-11 items-center gap-2 text-small text-ink">
            <input
              type="checkbox"
              className="size-4"
              checked={errorsOnly}
              onChange={(e) => {
                setErrorsOnly(e.target.checked);
                setPage(0);
              }}
            />
            Chỉ lượt không thành công
          </label>
        </div>
        <Pager page={page} hasMore={hasMore} onPage={setPage} />
      </div>
      <TableShell
        headers={["Lúc", "Kênh", "Model", "Bước", "Thời gian", "Token", "Kết cục", ""]}
        minWidth={900}
      >
        {rows.length === 0 && <EmptyRow colSpan={8} text="Chưa có lượt nào được ghi" />}
        {rows.map((row) => (
          <tr
            key={row.turn_id}
            className="border-b border-line/60 last:border-0 hover:bg-row-hover"
          >
            <td className="px-4 py-3 whitespace-nowrap text-ink-soft">
              {formatTime(row.started_at)}
            </td>
            <td className="px-4 py-3">
              {row.channel ? (
                <Badge>{row.channel}</Badge>
              ) : (
                <span className="text-ink-soft">-</span>
              )}
            </td>
            <td className="px-4 py-3 text-ink-soft">{row.model}</td>
            <td className="px-4 py-3 text-ink-soft">{row.steps}</td>
            <td className="px-4 py-3 whitespace-nowrap text-ink-soft">
              {formatDuration(row.duration_ms)}
            </td>
            <td className="px-4 py-3 text-ink-soft">{formatCount(totalTokens(row))}</td>
            <td className="px-4 py-3">
              <Outcome stop={row.stop} errorKind={row.error_kind} />
            </td>
            <td className="px-4 py-3 text-right">
              <Button
                variant="quiet"
                aria-label={`Xem các bước của lượt lúc ${formatTime(row.started_at)}`}
                onClick={() => setOpenId(row.turn_id)}
              >
                Xem
              </Button>
            </td>
          </tr>
        ))}
      </TableShell>
      {openId && <TurnSheet turnId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function Outcome({ stop, errorKind }: { stop: string; errorKind: string | null }) {
  const label = stopLabel(stop);
  const why = errorLabel(errorKind);
  return (
    <span className="flex flex-col items-start gap-0.5">
      <Badge tone={stop === "completed" ? "success" : "danger"}>{label}</Badge>
      {why && <span className="text-label text-danger">{why}</span>}
    </span>
  );
}

function TurnSheet({ turnId, onClose }: { turnId: string; onClose: () => void }) {
  const [turn, setTurn] = useState<TurnDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stale = false;
    api
      .get<TurnDetail>(`${TRACES_PATH}/${turnId}`)
      .then((found) => {
        if (!stale) setTurn(found);
      })
      .catch((err: unknown) => {
        if (!stale) setError(err instanceof Error ? err.message : "Không tải được");
      });
    return () => {
      stale = true;
    };
  }, [turnId]);

  return (
    <Sheet
      title="Các bước của lượt"
      subtitle={turn ? `${turn.model} · ${formatTime(turn.started_at)}` : undefined}
      onClose={onClose}
      wide
      footer={
        turn ? (
          <Link href={sessionHref(turn.session_id)} className={buttonClass("secondary")}>
            Xem phiên chat
          </Link>
        ) : undefined
      }
    >
      {error && <Notice tone="danger">{error}</Notice>}
      {!turn && !error && <p className="text-small text-ink-soft">Đang tải...</p>}
      {turn && <TurnBody turn={turn} />}
    </Sheet>
  );
}

function TurnBody({ turn }: { turn: TurnDetail }) {
  const why = errorLabel(turn.error_kind);
  const extra = [
    turn.cache_read_tokens > 0 && `${formatCount(turn.cache_read_tokens)} token từ cache`,
    turn.reasoning_tokens > 0 && `${formatCount(turn.reasoning_tokens)} token suy nghĩ`,
    turn.compactions > 0 && `${turn.compactions} lần rút gọn ngữ cảnh`,
  ].filter(Boolean);
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-2 text-small text-ink-soft">
        <Outcome stop={turn.stop} errorKind={turn.error_kind} />
        <span>
          {turn.steps} bước · {formatDuration(turn.duration_ms)} · {formatCount(turn.input_tokens)}{" "}
          vào / {formatCount(turn.output_tokens)} ra
        </span>
      </p>
      {extra.length > 0 && <p className="text-label text-ink-soft">{extra.join(" · ")}</p>}
      {why && <Notice tone="danger">{why}</Notice>}
      {turn.events.length === 0 && (
        <p className="text-small text-ink-soft">Lượt này không có bước nào được ghi.</p>
      )}
      <ol className="space-y-2">
        {turn.events.map((event, index) => (
          <li
            key={index}
            className={`rounded-tile border p-3 ${event.is_error ? "border-danger-line bg-danger-soft" : "border-line"}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">Bước {event.step}</Badge>
              <b className="text-body text-ink">{eventLabel(event.kind)}</b>
              {event.name && <span className="text-small text-ink">{event.name}</span>}
              <span className="text-label text-ink-soft">{formatDuration(event.duration_ms)}</span>
              {event.is_error && <Badge tone="danger">Lỗi</Badge>}
            </div>
            {Object.keys(event.detail).length > 0 && (
              <p className="mt-1.5 text-label break-words text-ink-soft">
                {detailText(event.detail)}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
