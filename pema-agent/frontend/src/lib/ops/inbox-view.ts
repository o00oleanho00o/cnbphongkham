// What the shared Inbox shows, as pure functions so the sentences and the filters are tested without a screen.
// The BE decides who may claim, take over or assign (`thread.claim`, `thread.assign`); this only reads the
// holder a conversation carries and words it.
//
// Known gap (O5 report): `ConversationSummary` has no `account_id` and `GET /conversations` has no account or
// "unassigned" filter, so the queue tab and the identity filter work on the rows already loaded. A row that
// does carry `account_id` (a later BE) is matched exactly; one that does not is matched by the channel of the
// identity, which is exact whenever the clinic has one customer identity on that channel.
import type { Schemas } from "@/lib/api";

type Summary = Schemas["ConversationSummary"];
type Identity = Schemas["IdentityOut"];

export type InboxTab = "queue" | "mine" | "all";
export const INBOX_TABS: readonly InboxTab[] = ["queue", "mine", "all"];
export const INBOX_TAB_LABEL: Record<InboxTab, string> = {
  queue: "Chờ nhận",
  mine: "Của tôi",
  all: "Tất cả",
};

export const ALL_IDENTITIES = "all";
export const ALL_IDENTITIES_LABEL = "Tất cả danh tính";

/** A row as the page uses it: the summary plus the identity id once the BE sends it. */
export type InboxRow = Summary & { account_id?: string | null };

export type HolderState = "unassigned" | "mine" | "other";

export function holderState(row: Pick<Summary, "assigned_user_id">, meId: string): HolderState {
  if (!row.assigned_user_id) return "unassigned";
  return row.assigned_user_id === meId ? "mine" : "other";
}

/** "#3F2A": four hex digits of the conversation id, the reference used in the team group. */
export function conversationCode(id: string): string {
  return `#${id.replaceAll("-", "").slice(0, 4).toUpperCase()}`;
}

export function isInTab(row: InboxRow, tab: InboxTab, meId: string): boolean {
  if (tab === "all") return true;
  if (tab === "mine") return holderState(row, meId) === "mine";
  return holderState(row, meId) === "unassigned" && row.status !== "closed";
}

export function tabCounts(rows: readonly InboxRow[], meId: string): Record<InboxTab, number> {
  return {
    queue: rows.filter((row) => isInTab(row, "queue", meId)).length,
    mine: rows.filter((row) => isInTab(row, "mine", meId)).length,
    all: rows.length,
  };
}

/** The customer-facing identity of a row, or null when it cannot be told (several on one channel). */
export function identityOf(row: InboxRow, identities: readonly Identity[]): Identity | null {
  if (row.account_id) return identities.find((i) => i.id === row.account_id) ?? null;
  const onChannel = identities.filter((i) => i.purpose === "customer" && i.channel === row.channel);
  return onChannel.length === 1 ? (onChannel[0] ?? null) : null;
}

export function matchesIdentity(
  row: InboxRow,
  identityId: string,
  identities: readonly Identity[],
): boolean {
  if (identityId === ALL_IDENTITIES) return true;
  if (row.account_id) return row.account_id === identityId;
  const wanted = identities.find((i) => i.id === identityId);
  return wanted !== undefined && wanted.channel === row.channel;
}

export function customerIdentities(identities: readonly Identity[]): Identity[] {
  return identities.filter((i) => i.purpose === "customer");
}

/** "Chưa ai nhận", "Bạn đang giữ" or "Mai Anh đang giữ". */
export function holderText(
  row: Pick<Summary, "assigned_user_id" | "assigned_user_name">,
  meId: string,
): string {
  const state = holderState(row, meId);
  if (state === "unassigned") return "Chưa ai nhận";
  if (state === "mine") return "Bạn đang giữ";
  return `${row.assigned_user_name ?? "Đồng nghiệp"} đang giữ`;
}

/** "#3F2A · Long", or just the code when the identity is not known. */
export function overLine(row: InboxRow, identities: readonly Identity[]): string {
  const identity = identityOf(row, identities);
  const code = conversationCode(row.id);
  return identity ? `${code} · ${identity.label}` : code;
}

/** URL of the Inbox: the open thread, the tab and the identity filter all live in it (they survive a reload). */
export function inboxHref(state: {
  conversationId?: string | null;
  tab?: InboxTab | null;
  identityId?: string | null;
}): string {
  const params = new URLSearchParams();
  if (state.conversationId) params.set("c", state.conversationId);
  if (state.tab) params.set("tab", state.tab);
  if (state.identityId && state.identityId !== ALL_IDENTITIES)
    params.set("identity", state.identityId);
  const query = params.toString();
  return query ? `/inbox?${query}` : "/inbox";
}

function isTab(value: string | null): value is InboxTab {
  return value !== null && (INBOX_TABS as readonly string[]).includes(value);
}

/** Reads the Inbox URL. `conversation` is the deep link the notifications carry. */
export function readInboxParams(
  params: URLSearchParams,
  canClaim: boolean,
): { conversationId: string | null; tab: InboxTab; identityId: string } {
  const tab = params.get("tab");
  return {
    conversationId: params.get("c") ?? params.get("conversation"),
    tab: isTab(tab) ? tab : canClaim ? "queue" : "all",
    identityId: params.get("identity") ?? ALL_IDENTITIES,
  };
}

/** Threads I held that somebody else holds now: the previous holder gets a toast (`assignment.changed`). */
export function takenOver(
  before: ReadonlyMap<string, string | null>,
  after: readonly Pick<Summary, "id" | "assigned_user_id" | "assigned_user_name">[],
  meId: string,
): { id: string; byName: string }[] {
  return after
    .filter((row) => before.get(row.id) === meId)
    .filter((row) => row.assigned_user_id !== null && row.assigned_user_id !== meId)
    .map((row) => ({ id: row.id, byName: row.assigned_user_name ?? "Đồng nghiệp" }));
}

/** Where a draft goes when the thread is locked: the placeholder of the disabled reply box. */
export function lockedPlaceholder(holderName: string | null | undefined): string {
  return `${holderName ?? "Đồng nghiệp"} đang phụ trách. Tiếp quản để nhắn khách.`;
}

/** "Hoàng Nam đang trả lời — Tiếp quản?" (the sentence the BE sends with 409 `thread_locked`). */
export function lockedNotice(holderName: string | null | undefined): string {
  return `${holderName ?? "Đồng nghiệp"} đang trả lời — Tiếp quản?`;
}

/** The line under the reply box: the customer sees the identity, never the operator. */
export function customerSeesLine(identityLabel: string | null | undefined): string {
  if (!identityLabel)
    return "Khách chỉ thấy tên danh tính của hội thoại, không thấy tên nhân viên.";
  return `Khách thấy tin này từ "${identityLabel}", không thấy tên nhân viên.`;
}

const KIND_TEXT: Record<Schemas["AssignmentKind"], string> = {
  claim: "nhận hội thoại",
  takeover: "tiếp quản",
  release: "trả hội thoại về hàng chờ",
  shift_end: "hết ca, hội thoại chuyển đi",
  assign: "giao hội thoại",
};

/** One line of "Lịch sử phụ trách". */
export function assignmentTitle(event: Schemas["AssignmentEventOut"]): string {
  const who = event.user_name ?? null;
  const previous = event.previous_user_name ?? null;
  if (event.kind === "claim") return `${who ?? "Một đồng nghiệp"} ${KIND_TEXT.claim}`;
  if (event.kind === "takeover") {
    return `${who ?? "Một đồng nghiệp"} ${KIND_TEXT.takeover}${previous ? ` từ ${previous}` : ""}`;
  }
  if (event.kind === "assign") {
    return who
      ? `${event.by ?? "Quản lý"} giao cho ${who}`
      : `${event.by ?? "Quản lý"} bỏ người phụ trách`;
  }
  if (event.kind === "release") return `${previous ?? "Người phụ trách"} ${KIND_TEXT.release}`;
  return `Hết ca: ${previous ?? "người phụ trách"} ${who ? `chuyển cho ${who}` : "trả hội thoại về hàng chờ"}`;
}
