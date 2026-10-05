"use client";

// One conversation of the Inbox: header, safety banners, messages, reply box.
// Safety (PLAN-AI01 section 5, patient_channel): a patient photo is NEVER analysed here. The backend flags
// the conversation and hands it to a person (review item `media_flag`); the UI only shows that flag and a
// placeholder where a message had no text. The AI draft shown in the thread is a draft, not a sent message.
// Several people at once: the thread reloads quietly when the page says it changed (`liveTick`), keeping the
// scroll position (it only follows new messages when you were already at the bottom) and the draft being typed;
// a presence beat tells colleagues you are viewing or replying, and theirs is shown as a warning, never a lock.
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Badge } from "@/components/admin/shared/ui-bits";
import { IconImageOff } from "@/components/admin/shared/ops-icons";
import { AssigneeStatus } from "@/components/ops/assignee-status";
import { conversationTitle } from "@/components/ops/inbox/conversation-list";
import { PresenceLine } from "@/components/ops/inbox/presence-line";
import {
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
  SecondaryButton,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, newIdempotencyKey, unwrap } from "@/lib/api/client";
import { viewersOf, type PresenceViewer } from "@/lib/live/live-types";
import { usePresenceHeartbeat } from "@/lib/live/use-presence-heartbeat";
import {
  OWNER_KEEP,
  initialOwnerValue,
  ownerIdFor,
  ownerOptions,
} from "@/lib/ops/assignee-options";
import { formatDateTime } from "@/lib/ops/format";
import { CONVERSATION_STATUS_LABEL, MESSAGE_STATUS_LABEL, SENDER_LABEL } from "@/lib/ops/labels";
import { presenceStateFor, presenceText, someoneReplying } from "@/lib/ops/presence-view";
import { useSession } from "@/lib/session/session-context";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

type Conversation = Schemas["ConversationOut"];
type Message = Schemas["MessageOut"];

const STATUS_OPTIONS: SelectOption[] = (
  Object.keys(CONVERSATION_STATUS_LABEL) as Schemas["ConversationStatus"][]
).map((value) => ({ value, label: CONVERSATION_STATUS_LABEL[value] }));

const MAX_REPLY = 2000;
/** Closer than this to the bottom counts as "reading the latest": new messages scroll into view. */
const NEAR_BOTTOM_PX = 80;

type Loaded = {
  conversation: Conversation;
  messages: Message[];
  flags: Schemas["ReviewItemOut"][];
};

function MessageBubble({ message }: { message: Message }) {
  const inbound = message.direction === "inbound";
  const draft = message.status === "draft";
  const system = message.sender_type === "system";
  const align = inbound ? "items-start" : "items-end";
  const tone = inbound
    ? "bg-surface border-line text-ink"
    : draft
      ? "border-2 border-dashed border-warning-line bg-warning-soft text-ink"
      : system
        ? "bg-tile text-ink-soft border-line"
        : "bg-brand-500 text-white border-brand-500";

  return (
    <li className={`flex flex-col gap-1 ${align}`}>
      <div
        className={`max-w-[88%] rounded-card border px-3.5 py-2.5 text-body leading-relaxed sm:max-w-[75%] ${tone}`}
      >
        {message.body === null ? (
          <span className="inline-flex items-center gap-2 text-small text-ink-soft">
            <IconImageOff size={18} />
            Tin không có chữ (ảnh hoặc tệp). Hệ thống không phân tích ảnh; nhân viên xem trực tiếp.
          </span>
        ) : (
          <span className="whitespace-pre-wrap">{message.body}</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 px-1 text-micro text-ink-soft">
        <span>{SENDER_LABEL[message.sender_type]}</span>
        <span>·</span>
        <span>{formatDateTime(message.created_at)}</span>
        {!inbound && <span>· {MESSAGE_STATUS_LABEL[message.status]}</span>}
        {draft && message.review_item_id && (
          <Link
            href={`/review?i=${message.review_item_id}`}
            className="font-medium text-brand-500 underline"
          >
            Mở nháp để duyệt
          </Link>
        )}
        {message.error_code && <Badge tone="red">Lỗi gửi</Badge>}
      </div>
    </li>
  );
}

export function ThreadView({
  conversationId,
  onChanged,
  liveTick = 0,
  listViewers,
}: {
  conversationId: string;
  /** The list should reload (status, unread or last message changed). */
  onChanged: () => void;
  /** Changes whenever the page learned (event or polling) that this conversation may have changed. */
  liveTick?: number;
  /** Presence as the list last saw it; preferred over the detail's own because the list refreshes on events. */
  listViewers?: readonly PresenceViewer[];
}) {
  const { user, can } = useSession();
  const toast = useToast();
  const [text, setText] = useState("");
  const [sendError, setSendError] = useState("");
  const [sending, setSending] = useState(false);
  const sendKey = useRef(newIdempotencyKey());
  const endRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const atBottom = useRef(true);
  const {
    staff,
    loading: staffLoading,
    error: staffError,
    reload: reloadStaff,
  } = useAssignableStaff();

  const load = useCallback(
    async (signal: AbortSignal): Promise<Loaded> => {
      const path = { conversation_id: conversationId };
      const [conversation, page, flags] = await Promise.all([
        unwrap(http.GET("/api/v1/conversations/{conversation_id}", { params: { path }, signal })),
        unwrap(
          http.GET("/api/v1/conversations/{conversation_id}/messages", {
            params: { path, query: { limit: 200 } },
            signal,
          }),
        ),
        can("review.read")
          ? unwrap(
              http.GET("/api/v1/review-items", {
                params: {
                  query: { conversation_id: conversationId, review_status: "pending", limit: 20 },
                },
                signal,
              }),
            )
          : Promise.resolve({ items: [] as Schemas["ReviewItemOut"][] }),
      ]);
      return { conversation, messages: page.items, flags: flags.items };
    },
    [conversationId, can],
  );
  const { data, error, loading, reload, refresh, setData } = useLoad(load);

  const seenTick = useRef(liveTick);
  useEffect(() => {
    if (liveTick === seenTick.current) return;
    seenTick.current = liveTick;
    refresh();
  }, [liveTick, refresh]);

  usePresenceHeartbeat(conversationId, presenceStateFor(text));

  const unread = data?.conversation.unread_count ?? 0;
  useEffect(() => {
    if (unread === 0) return;
    unwrap(
      http.POST("/api/v1/conversations/{conversation_id}/read", {
        params: { path: { conversation_id: conversationId } },
      }),
    )
      .then(onChanged)
      .catch(() => undefined);
  }, [unread, conversationId, onChanged]);

  const messageCount = data?.messages.length ?? 0;
  useEffect(() => {
    // A new message only pulls the view down when the person was already reading the latest one.
    if (!atBottom.current) return;
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messageCount, conversationId]);

  const trackScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
  }, []);

  const mediaFlags = useMemo(
    () => data?.flags.filter((f) => f.kind === "media_flag") ?? [],
    [data],
  );
  const redFlags = useMemo(
    () => data?.flags.filter((f) => f.risk_level === "red_flag") ?? [],
    [data],
  );

  async function patchConversation(
    change: Partial<Pick<Conversation, "assigned_user_id" | "status">>,
  ) {
    if (!data) return;
    try {
      const updated = await unwrap(
        http.PATCH("/api/v1/conversations/{conversation_id}", {
          params: { path: { conversation_id: conversationId } },
          body: { ...change, version: data.conversation.version },
        }),
      );
      setData({ ...data, conversation: updated });
      onChanged();
    } catch (e) {
      toast.push(
        "error",
        e instanceof ApiError && e.code === "version_conflict"
          ? "Hội thoại vừa được cập nhật, đã tải lại."
          : errorMessage(e),
      );
      reload();
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;
    setSending(true);
    setSendError("");
    try {
      await unwrap(
        http.POST("/api/v1/conversations/{conversation_id}/messages", {
          params: {
            path: { conversation_id: conversationId },
            header: { "Idempotency-Key": sendKey.current },
          },
          body: { text: body, proactive: false },
        }),
      );
      setText("");
      sendKey.current = newIdempotencyKey();
      reload();
      onChanged();
    } catch (err) {
      setSendError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  if (error && !data) return <RetryNotice message={error} onRetry={reload} />;
  if (!data) return loading ? <ListSkeleton rows={3} /> : null;

  const { conversation } = data;
  const closed = conversation.status === "closed";
  const canReply = can("conversation.reply");
  const mine = conversation.assigned_user_id === user.id;
  const viewers = listViewers ?? viewersOf(conversation);
  const ownerInput = {
    me: user,
    currentId: conversation.assigned_user_id,
    staff,
    keepWhenUnassigned: true,
    allowUnassign: true,
  };

  function changeOwner(value: string) {
    if (value === OWNER_KEEP) return;
    void patchConversation({
      assigned_user_id: ownerIdFor(value, user, conversation.assigned_user_id),
    });
  }

  return (
    <section className="flex min-h-[60dvh] flex-col rounded-card border border-line bg-surface shadow-card lg:max-h-[calc(100dvh-9rem)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-section font-semibold text-ink">
            {conversationTitle(conversation)}
          </h2>
          <p className="text-label text-ink-soft">
            {conversation.patient_id ? (
              <Link
                href={`/patients/${conversation.patient_id}`}
                className="text-brand-500 underline"
              >
                Xem hồ sơ {conversation.patient_code}
              </Link>
            ) : (
              "Chưa gắn hồ sơ bệnh nhân"
            )}
          </p>
          <PresenceLine viewers={viewers} className="mt-1" />
        </div>
        {canReply && (
          <div className="grid w-full gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center">
            {!mine && (
              <SecondaryButton
                onClick={() => void patchConversation({ assigned_user_id: user.id })}
              >
                Nhận xử lý
              </SecondaryButton>
            )}
            <div className="sm:w-64">
              <SelectMenu
                size="md"
                ariaLabel="Phụ trách hội thoại"
                prefix="Phụ trách:"
                value={initialOwnerValue(ownerInput)}
                options={ownerOptions(ownerInput)}
                onChange={changeOwner}
              />
              <AssigneeStatus loading={staffLoading} error={staffError} onRetry={reloadStaff} />
            </div>
            <div className="sm:w-44">
              <SelectMenu
                size="md"
                ariaLabel="Trạng thái hội thoại"
                value={conversation.status}
                options={STATUS_OPTIONS}
                onChange={(value) =>
                  void patchConversation({ status: value as Schemas["ConversationStatus"] })
                }
              />
            </div>
          </div>
        )}
      </header>

      <div className="space-y-2 px-4 pt-3 empty:hidden">
        {!conversation.patient_id && (
          <Notice tone="warn">
            Khách chưa được xác minh với hồ sơ nào. Trợ lý AI không được nhắc tên, lịch hẹn hay
            thuốc cho đến khi nhân viên xác nhận danh tính.
          </Notice>
        )}
        {redFlags.length > 0 && (
          <Notice
            tone="error"
            action={
              <Link
                href={`/review?i=${redFlags[0]?.id}`}
                className="text-small font-semibold underline"
              >
                Mở cảnh báo
              </Link>
            }
          >
            Có dấu hiệu cần bác sĩ ({redFlags[0]?.red_flags?.join(", ")}). Trợ lý AI không trả lời;
            cần người liên hệ khách.
          </Notice>
        )}
        {mediaFlags.length > 0 && (
          <Notice
            tone="warn"
            action={
              <Link
                href={`/review?i=${mediaFlags[0]?.id}`}
                className="text-small font-semibold underline"
              >
                Mở mục xử lý
              </Link>
            }
          >
            Khách gửi ảnh hoặc tệp: đã chuyển nhân viên. Hệ thống không phân tích ảnh, hãy xem ảnh
            trong ứng dụng Zalo rồi quyết định bước tiếp theo.
          </Notice>
        )}
      </div>

      <ol
        ref={listRef}
        onScroll={trackScroll}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
        aria-label="Tin nhắn"
      >
        {data.messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={endRef} />
      </ol>

      {canReply && (
        <form onSubmit={(e) => void send(e)} className="border-t border-line p-3">
          {someoneReplying(viewers) && (
            <div className="mb-2">
              <Notice tone="warn">
                {presenceText(viewers.filter((v) => v.state === "replying"))}. Bạn vẫn nhắn được,
                nhưng hãy hỏi đồng nghiệp trước để khách không nhận hai tin trùng nhau.
              </Notice>
            </div>
          )}
          {sendError && (
            <div className="mb-2">
              <Notice tone="error">{sendError}</Notice>
            </div>
          )}
          <label htmlFor="reply-text" className="sr-only">
            Nội dung trả lời
          </label>
          <textarea
            id="reply-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter")
                e.currentTarget.form?.requestSubmit();
            }}
            maxLength={MAX_REPLY}
            rows={2}
            disabled={closed}
            placeholder={
              closed ? "Hội thoại đã đóng, mở lại để nhắn." : "Nhập tin trả lời khách..."
            }
            className={cx(FIELD_BASE_CLASS, "w-full resize-y")}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-label text-ink-soft">
              {text.length}/{MAX_REPLY} · Tin do nhân viên soạn và gửi.
            </span>
            <PrimaryButton type="submit" disabled={sending || closed || !text.trim()}>
              {sending ? "Đang gửi..." : "Gửi"}
            </PrimaryButton>
          </div>
        </form>
      )}
    </section>
  );
}
