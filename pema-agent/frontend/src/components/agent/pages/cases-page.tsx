// Ca của agent: the proactive work its plugins opened (appointment reminders, follow-ups), newest first, each with
// its log on demand and, while it is live, "Chạy ngay": the case runs at the agent's next pass instead of waiting for
// its hour. Its checks still run (hours, daily cap, the customer's silence), so it may wait again without writing.
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  type KitTone,
  Notice,
  PageHeader,
} from "@/components/agent/plugin-kit";
import { ApiError, agentApi as api } from "@/lib/agent/api";
import {
  type AgentCase,
  CASES_PATH,
  type CaseEvent,
  type CaseStatus,
  casePath,
  EVENT_LABELS,
  isCaseList,
  isLive,
  KIND_LABELS,
  STATUS_LABELS,
  WAIT_LABELS,
  wakePath,
} from "@/lib/agent/agent-cases";

type Message = { tone: KitTone; text: string };

const STATUS_TONES: Record<CaseStatus, KitTone> = {
  open: "info",
  waiting: "warning",
  needs_human: "danger",
  done: "success",
  stopped: "neutral",
};

const errorText = (err: unknown) => (err instanceof Error ? err.message : "Lỗi");

const when = (iso: string | null) =>
  iso === null
    ? "-"
    : new Date(iso).toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        dateStyle: "short",
        timeStyle: "short",
      });

function waitText(item: AgentCase): string {
  if (!isLive(item)) return item.end_reason ?? "";
  if (item.status === "open") return "Chạy ở lượt quét tới";
  const what = WAIT_LABELS[item.wait_for ?? ""] ?? item.wait_for ?? "";
  return item.wake_at ? `Chờ ${what}, tới ${when(item.wake_at)}` : `Chờ ${what}`;
}

function accept(answer: unknown): AgentCase[] {
  if (!isCaseList(answer)) throw new Error("Câu trả lời của agent không đúng dạng.");
  return answer.cases;
}

export function CasesPage() {
  const [cases, setCases] = useState<AgentCase[] | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState("");
  const [opened, setOpened] = useState<{ id: number; events: CaseEvent[] } | null>(null);

  const load = useCallback(async () => setCases(accept(await api.get<unknown>(CASES_PATH))), []);

  useEffect(() => {
    load().catch((err: unknown) => setMessage({ tone: "danger", text: errorText(err) }));
  }, [load]);

  async function run(label: string, work: () => Promise<Message | null>) {
    setBusy(label);
    setMessage(null);
    try {
      setMessage(await work());
    } catch (err) {
      setMessage({ tone: "danger", text: errorText(err) });
    } finally {
      setBusy("");
    }
  }

  const wake = (item: AgentCase) =>
    run(`wake-${item.id}`, async () => {
      const refused = await api.post(wakePath(item.id)).then(
        () => false,
        (err: unknown) => {
          if (err instanceof ApiError && err.status === 409) return true;
          throw err;
        },
      );
      await load();
      if (refused)
        return { tone: "warning", text: `Ca #${item.id} đã đóng hoặc plugin của nó đang tắt.` };
      return {
        tone: "success",
        text: `Ca #${item.id} sẽ chạy trong vài giây. Các bước kiểm vẫn chạy, nên ca có thể chờ tiếp mà chưa nhắn.`,
      };
    });

  const reload = () =>
    run("reload", async () => {
      await load();
      return null;
    });

  const toggleLog = async (item: AgentCase) => {
    if (opened?.id === item.id) {
      setOpened(null);
      return;
    }
    await run(`log-${item.id}`, async () => {
      const found = await api.get<{ events: CaseEvent[] }>(casePath(item.id));
      setOpened({ id: item.id, events: found.events });
      return null;
    });
  };

  if (!cases) {
    return (
      <div>
        <PageHeader title="Ca" />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ca"
        subtitle="Việc agent tự làm theo thời gian: nhắc lịch, chăm sóc lại. Chạy ngay cho ca chạy ở lượt quét tới thay vì chờ tới giờ; các bước kiểm vẫn chạy."
        aside={
          <Button variant="secondary" busy={busy === "reload"} onClick={reload}>
            Tải lại
          </Button>
        }
      />
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      <Card
        title="Danh sách ca"
        aside={<span className="text-small text-ink-soft">{cases.length} ca</span>}
      >
        {cases.length === 0 ? (
          <Empty>
            Chưa có ca nào. Ca mở khi plugin cần làm việc chủ động (ví dụ agent vừa trả lời một
            khách trên kênh được chăm sóc lại). Ca chỉ chạy khi "Bật ca chủ động" ở trang Cài đặt
            đang bật.
          </Empty>
        ) : (
          <ul aria-label="Danh sách ca" className="divide-y divide-line">
            {cases.map((item) => (
              <li key={item.id}>
                <CaseRow
                  item={item}
                  busy={busy}
                  events={opened?.id === item.id ? opened.events : null}
                  onWake={() => wake(item)}
                  onLog={() => toggleLog(item)}
                />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function CaseRow({
  item,
  busy,
  events,
  onWake,
  onLog,
}: {
  item: AgentCase;
  busy: string;
  events: CaseEvent[] | null;
  onWake: () => void;
  onLog: () => void;
}) {
  const kind = KIND_LABELS[item.kind] ?? item.kind;
  return (
    <div className="px-1 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1 basis-64">
          <p className="truncate font-semibold text-ink">
            #{item.id} · {kind}{" "}
            <span className="font-normal text-ink-soft">· bước {item.node}</span>
          </p>
          <p className="truncate text-small text-ink-soft">
            {item.channel} · {item.conversation_id} · đã nhắn {item.proactive_sent} ·{" "}
            {waitText(item)}
          </p>
        </div>
        <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
        <div className="flex flex-wrap gap-2">
          {isLive(item) && (
            <Button
              variant="secondary"
              aria-label={`Chạy ngay ca #${item.id}`}
              busy={busy === `wake-${item.id}`}
              onClick={onWake}
            >
              Chạy ngay
            </Button>
          )}
          <Button
            variant="ghost"
            aria-label={`${events ? "Ẩn" : "Xem"} nhật ký ca #${item.id}`}
            busy={busy === `log-${item.id}`}
            onClick={onLog}
          >
            {events ? "Ẩn nhật ký" : "Nhật ký"}
          </Button>
        </div>
      </div>
      {events && (
        <ol
          aria-label={`Nhật ký ca #${item.id}`}
          className="mt-2 space-y-1 border-l border-line pl-3"
        >
          {events.map((event) => (
            <li key={event.seq} className="text-small text-ink-soft">
              <span className="text-ink">{when(event.at)}</span> ·{" "}
              {EVENT_LABELS[event.kind] ?? event.kind}
              {event.node ? ` · ${event.node}` : ""} · <code>{JSON.stringify(event.detail)}</code>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
