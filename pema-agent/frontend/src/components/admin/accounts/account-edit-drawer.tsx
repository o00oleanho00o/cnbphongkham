// ported from: web/src/pages/account-edit-drawer.tsx
//
// Deviations: DTOs are the contract's (snake_case `AccountOut`, `AgentOut`, `ReactionIcon`) and the
// original `loai` ("ca_nhan" | "bot") is `channel` (`zalo_personal` | `zalo_bot` | `zalo_oa`; `zalo_oa`
// is listed but disabled: not supported yet). `ReactionIcon` has no `label`, so the tooltip is its key.
// The inline `onChange` arrows became `setField` calls with stable callbacks. NEW: "Hồ sơ chính sách"
// (policy profile) select, saved through `PUT /admin/policy/accounts/{id}` and shown only when
// `can("admin.policy")`; on create the profile goes in the create body.
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { MO_TA_KENH, MO_TA_KENH_OA } from "@/lib/admin/accounts/mo-ta-loai-kenh";
import {
  CANH_BAO_CHUYEN_SANG_TRO_LY,
  CANH_BAO_HO_SO,
  HO_SO_MAC_DINH,
  MO_TA_HO_SO,
  NHAN_HO_SO,
} from "@/lib/admin/accounts/policy-profile-text";
import { http, unwrap, errorMessage } from "@/lib/api/client";
import type { Account, Agent, Schemas } from "@/lib/api";
import { useSession } from "@/lib/session/session-context";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { ToggleKnob } from "@/components/admin/shared/ui-bits";

type ChannelKind = Schemas["ChannelKind"];
type AllowlistMode = Schemas["AllowlistMode"];
type PolicyProfileKey = Schemas["PolicyProfileKey"];
type ReactionIcon = Schemas["ReactionIcon"];

type Form = {
  id: string;
  label: string;
  agentId: string;
  groupRequireMention: boolean;
  respondToGroups: boolean;
  groupPassiveListen: boolean;
  autoReactEnabled: boolean;
  autoReactIcon: string;
  typingIndicatorEnabled: boolean;
  autoAcceptFriends: boolean;
  autoAcceptFriendDelayMinutes: number;
  allowlistMode: AllowlistMode;
  allowlistIds: string;
  /** Chốt LÚC TẠO, không đổi được sau đó - xem `AccountCreate.channel` của contract */
  channel: ChannelKind;
  /** Hồ sơ chính sách (NEW): patient_channel là mặc định an toàn */
  policyProfile: PolicyProfileKey;
};

type BooleanField =
  | "respondToGroups"
  | "groupRequireMention"
  | "groupPassiveListen"
  | "typingIndicatorEnabled"
  | "autoReactEnabled"
  | "autoAcceptFriends";

const CHANNELS: readonly ChannelKind[] = ["zalo_bot", "zalo_personal", "zalo_oa"];
const ALLOWLIST_MODES: readonly AllowlistMode[] = ["all", "list"];
const POLICY_KEYS: readonly PolicyProfileKey[] = ["patient_channel", "staff_assistant"];

function isChannelKind(v: string): v is ChannelKind {
  return (CHANNELS as readonly string[]).includes(v);
}
function isAllowlistMode(v: string): v is AllowlistMode {
  return (ALLOWLIST_MODES as readonly string[]).includes(v);
}
function isPolicyKey(v: string): v is PolicyProfileKey {
  return (POLICY_KEYS as readonly string[]).includes(v);
}

/**
 * Danh sách cho phép mặc định theo loại kênh. Tài khoản bot ĐÓNG sẵn (xem `doiLoai`); Zalo OA cũng
 * đóng vì chưa hỗ trợ và không nên có đường mở.
 */
const ALLOWLIST_MAC_DINH: Record<ChannelKind, AllowlistMode> = {
  zalo_bot: "list",
  zalo_personal: "all",
  zalo_oa: "list",
};

/*
 * Hint NGẮN: đoạn giải thích đầy đủ đã nằm ngay dưới ô chọn, nên
 * hint dài chỉ lặp lại và đẩy popup rộng quá drawer.
 */
const CHANNEL_OPTIONS: SelectOption[] = [
  { value: "zalo_personal", label: "Tài khoản cá nhân", hint: "quét QR" },
  { value: "zalo_bot", label: "Tài khoản bot chính thức", hint: "nhập token" },
  { value: "zalo_oa", label: "Zalo OA", hint: "chưa hỗ trợ", disabled: true },
];

const ALLOWLIST_OPTIONS: SelectOption[] = [
  { value: "all", label: "Trả lời tất cả mọi người" },
  { value: "list", label: "Chỉ trả lời user ID trong danh sách" },
];

const POLICY_OPTIONS: SelectOption[] = POLICY_KEYS.map((key) => ({
  value: key,
  label: NHAN_HO_SO[key],
  hint: key === HO_SO_MAC_DINH ? "mặc định" : undefined,
}));

const SECTION_TITLE = "text-micro font-semibold uppercase tracking-wider text-ink-soft";
const INPUT_CLASS = "gc-input w-full max-sm:min-h-11";

function Toggle({
  field,
  value,
  onChange,
  label,
  hint,
}: {
  field: BooleanField;
  value: boolean;
  onChange: (field: BooleanField, v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(field, !value)}
      className="flex w-full items-center justify-between gap-3 py-1 text-left max-sm:min-h-11"
    >
      <span>
        <span className="block text-small font-medium text-ink">{label}</span>
        {hint && <span className="block text-label leading-[1.6] text-ink-soft">{hint}</span>}
      </span>
      <ToggleKnob on={value} />
    </button>
  );
}

function initialForm(account: Account | null, agents: Agent[]): Form {
  const channel = account?.channel ?? "zalo_personal";
  return {
    id: account?.id ?? "",
    label: account?.label ?? "",
    agentId: account?.agent_id ?? agents.find((a) => a.is_default)?.id ?? agents[0]?.id ?? "",
    groupRequireMention: account?.group_require_mention ?? true,
    respondToGroups: account?.respond_to_groups ?? true,
    groupPassiveListen: account?.group_passive_listen ?? true,
    autoReactEnabled: account?.auto_react_enabled ?? true,
    autoReactIcon: account?.auto_react_icon ?? "heart",
    typingIndicatorEnabled: account?.typing_indicator_enabled ?? true,
    autoAcceptFriends: account?.auto_accept_friends ?? false,
    autoAcceptFriendDelayMinutes: account?.auto_accept_friend_delay_minutes ?? 1,
    allowlistMode: account?.allowlist?.mode ?? ALLOWLIST_MAC_DINH[channel],
    allowlistIds: (account?.allowlist?.user_ids ?? []).join("\n"),
    channel,
    policyProfile: account?.policy_profile ?? HO_SO_MAC_DINH,
  };
}

/** Khối "Thả cảm xúc": kênh bot có câu giải thích, Zalo OA không có mục này, kênh cá nhân có ô chọn. */
function ReactionSection({
  form,
  reactionIcons,
  onToggle,
  onPickIcon,
}: {
  form: Form;
  reactionIcons: ReactionIcon[];
  onToggle: (field: BooleanField, v: boolean) => void;
  onPickIcon: (key: string) => void;
}) {
  if (form.channel === "zalo_oa") return null;
  /* Kênh bot KHÔNG thả được cảm xúc (`setMessageReaction` trả 404).
     Để ô này hiện thì người vận hành bật xong tưởng có, mà chẳng
     bao giờ thấy cảm xúc nào - cùng lớp lỗi với việc trang Tools
     từng hiện "Gửi file" xanh cho tài khoản bot. */
  if (form.channel === "zalo_bot") {
    return (
      <p className="py-1 text-small leading-[1.6] text-ink-soft">
        <span className="font-medium text-ink">Thả cảm xúc khi nhận tin</span> - Zalo Bot API không
        có method thả cảm xúc nên tài khoản bot không dùng được mục này.
      </p>
    );
  }
  return (
    <>
      <Toggle
        field="autoReactEnabled"
        value={form.autoReactEnabled}
        onChange={onToggle}
        label="Thả cảm xúc khi nhận tin"
        hint="Báo cho người nhắn biết bot đã thấy tin"
      />
      {form.autoReactEnabled && reactionIcons.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {reactionIcons.map((icon) => (
            <button
              key={icon.key}
              type="button"
              title={icon.key}
              aria-label={icon.key}
              aria-pressed={form.autoReactIcon === icon.key}
              onClick={() => onPickIcon(icon.key)}
              className={`flex h-11 w-11 items-center justify-center rounded-control border text-section transition-colors sm:h-9 sm:w-9 ${
                form.autoReactIcon === icon.key
                  ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100"
                  : "border-line hover:bg-tile"
              }`}
            >
              {icon.emoji}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/** Ô chọn hồ sơ chính sách + hai dòng giải thích mỗi hồ sơ + cảnh báo (NEW) */
function PolicyProfileSection({
  value,
  initial,
  onChange,
}: {
  value: PolicyProfileKey;
  initial: PolicyProfileKey;
  onChange: (v: string) => void;
}) {
  const [first, second] = MO_TA_HO_SO[value];
  const goingDirect = value === "staff_assistant" && initial !== "staff_assistant";
  return (
    <div className="space-y-2 rounded-tile border border-line p-4">
      <div className={SECTION_TITLE}>Hồ sơ chính sách</div>
      <SelectMenu
        size="md"
        value={value}
        options={POLICY_OPTIONS}
        onChange={onChange}
        ariaLabel="Hồ sơ chính sách"
      />
      <p className="text-label leading-[1.6] text-ink-soft">{first}</p>
      <p className="text-label leading-[1.6] text-ink-soft">{second}</p>
      <p className="rounded-control bg-warning-soft px-3 py-2 text-label leading-[1.6] text-warning">
        {CANH_BAO_HO_SO}
      </p>
      {goingDirect && (
        <p className="text-label leading-[1.6] font-medium text-danger">
          {CANH_BAO_CHUYEN_SANG_TRO_LY}
        </p>
      )}
    </div>
  );
}

/** Drawer tạo/sửa account: tên, não, policies. account=null nghĩa là tạo mới. */
export function AccountEditDrawer({
  account,
  agents,
  onClose,
  onSaved,
}: {
  account: Account | null;
  agents: Agent[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { can } = useSession();
  const canPolicy = can("admin.policy");
  const [form, setForm] = useState<Form>(() => initialForm(account, agents));
  /** Token bot nhập mới; rỗng = không đụng tới token đã lưu */
  const [botToken, setBotToken] = useState("");
  /**
   * Id đã TẠO XONG trong chính lần mở drawer này.
   *
   * `save()` chạy ba bước (create -> update -> lưu token) và bước cuối có thể
   * hỏng riêng (server kiểm token với Zalo). Hỏng thì drawer đứng nguyên với
   * `account` vẫn null, nên bấm lại là gọi `create()` lần hai và ăn 409
   * "Account id đã tồn tại" - đọc ngay sau khi tự tay tạo nó trong chính drawer
   * này thì không ai hiểu chuyện gì.
   */
  const [daTao, setDaTao] = useState<string | null>(null);
  const [reactionIcons, setReactionIcons] = useState<ReactionIcon[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nen = useChotNen(onClose);

  useEffect(() => {
    let cancelled = false;
    unwrap(http.GET("/api/v1/admin/accounts/reaction-icons"))
      .then((items) => {
        if (!cancelled) setReactionIcons(items);
      })
      .catch(() => {
        if (!cancelled) setReactionIcons([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setField = useCallback(<K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((truoc) => ({ ...truoc, [key]: value }));
  }, []);

  const setBoolean = useCallback(
    (field: BooleanField, value: boolean) => setField(field, value),
    [setField],
  );

  /**
   * Đổi loại kênh thì đặt lại mặc định danh sách cho phép.
   *
   * Tài khoản bot ĐÓNG sẵn: bán kính khác hẳn tài khoản cá nhân - nick cá nhân
   * phải là bạn bè mới nhắn được, còn bot thì ai có link cũng nhắn được. Server
   * cũng đặt mặc định này lúc tạo, nhưng drawer gọi `update()` NGAY sau `create()`
   * nên không đồng bộ ở đây là ghi đè mất mặc định an toàn vừa đặt.
   */
  const doiLoai = useCallback((value: string) => {
    if (!isChannelKind(value)) return;
    setForm((truoc) => ({
      ...truoc,
      channel: value,
      allowlistMode: ALLOWLIST_MAC_DINH[value],
    }));
  }, []);

  const onAgent = useCallback((agentId: string) => setField("agentId", agentId), [setField]);
  const onAllowlistMode = useCallback(
    (value: string) => {
      if (isAllowlistMode(value)) setField("allowlistMode", value);
    },
    [setField],
  );
  const onPolicy = useCallback(
    (value: string) => {
      if (isPolicyKey(value)) setField("policyProfile", value);
    },
    [setField],
  );
  const onPickIcon = useCallback((key: string) => setField("autoReactIcon", key), [setField]);

  const agentOptions = useMemo<SelectOption[]>(
    () =>
      agents.map((a) => ({
        value: a.id,
        label: `${a.icon} ${a.name}`,
        hint: a.is_default ? "mặc định" : undefined,
      })),
    [agents],
  );

  async function save() {
    setBusy(true);
    setError("");
    const patch: Schemas["AccountUpdate"] = {
      label: form.label,
      agent_id: form.agentId || null,
      group_require_mention: form.groupRequireMention,
      respond_to_groups: form.respondToGroups,
      group_passive_listen: form.groupPassiveListen,
      auto_react_enabled: form.autoReactEnabled,
      auto_react_icon: form.autoReactIcon,
      typing_indicator_enabled: form.typingIndicatorEnabled,
      auto_accept_friends: form.autoAcceptFriends,
      auto_accept_friend_delay_minutes: form.autoAcceptFriendDelayMinutes,
      allowlist: {
        mode: form.allowlistMode,
        user_ids: form.allowlistIds
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      },
    };
    const accountId = account?.id ?? daTao ?? form.id;
    try {
      if (!account && !daTao) {
        await unwrap(
          http.POST("/api/v1/admin/accounts", {
            body: {
              id: form.id,
              label: form.label,
              agent_id: form.agentId || null,
              channel: form.channel,
              // Không có quyền chọn hồ sơ thì để BE đặt mặc định (patient_channel)
              policy_profile: canPolicy ? form.policyProfile : HO_SO_MAC_DINH,
            },
          }),
        );
        setDaTao(form.id);
      }
      await unwrap(
        http.PATCH("/api/v1/admin/accounts/{account_id}", {
          params: { path: { account_id: accountId } },
          body: patch,
        }),
      );
      // Hồ sơ chính sách đi đường riêng (có audit riêng ở BE); lúc tạo đã nằm trong body create
      if (account && canPolicy && form.policyProfile !== account.policy_profile) {
        await unwrap(
          http.PUT("/api/v1/admin/policy/accounts/{account_id}", {
            params: { path: { account_id: accountId } },
            body: { policy_profile: form.policyProfile },
          }),
        );
      }
      // Token lưu SAU cùng và qua đường riêng: server kiểm với API Zalo trước
      // khi lưu, nên bước này có thể hỏng riêng mà phần cấu hình vẫn đã lưu xong.
      if (form.channel === "zalo_bot" && botToken.trim()) {
        await unwrap(
          http.PUT("/api/v1/admin/accounts/{account_id}/bot-token", {
            params: { path: { account_id: accountId } },
            body: { token: botToken.trim() },
          }),
        );
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const isBot = form.channel === "zalo_bot";

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/25 backdrop-blur-[2px]" {...nen}>
      <div
        className="flex h-full w-full max-w-md flex-col border-l border-line bg-surface"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 font-semibold break-words text-ink">
            {account ? `Sửa: ${account.label}` : "Thêm account Zalo"}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile max-sm:min-h-11"
          >
            Đóng
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!account && (
            <div>
              <label className="mb-1.5 block text-small font-medium text-ink">
                ID{" "}
                <span className="font-normal text-ink-soft">
                  (kebab-case, dùng làm thư mục data)
                </span>
              </label>
              <input
                className={INPUT_CLASS}
                value={form.id}
                onChange={(e) => setField("id", e.target.value)}
                placeholder="vd: acc-cham-soc"
              />
            </div>
          )}

          {!account && (
            <div>
              <label className="mb-1.5 block text-small font-medium text-ink">Loại kênh</label>
              <SelectMenu
                size="md"
                value={form.channel}
                options={CHANNEL_OPTIONS}
                onChange={doiLoai}
                ariaLabel="Loại kênh"
              />
              <p className="mt-1.5 text-label leading-[1.6] text-ink-soft">
                {MO_TA_KENH[form.channel]}
              </p>
              <p className="mt-1 text-label text-ink-soft">Chốt lúc tạo, không đổi được sau đó.</p>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-small font-medium text-ink">Tên hiển thị</label>
            <input
              className={INPUT_CLASS}
              value={form.label}
              onChange={(e) => setField("label", e.target.value)}
              placeholder="vd: Nick chăm sóc khách hàng"
            />
          </div>

          {isBot && (
            <div>
              <label className="mb-1.5 block text-small font-medium text-ink">
                Token bot{" "}
                {account?.has_bot_token && (
                  <span className="font-normal text-ink-soft">(đã có - nhập mới để thay)</span>
                )}
              </label>
              <input
                type="password"
                autoComplete="off"
                className={`${INPUT_CLASS} font-mono`}
                value={botToken}
                onChange={(e) => setBotToken(e.target.value)}
                placeholder={account?.has_bot_token ? "Để trống nếu không đổi" : "123456789:..."}
              />
              <p className="mt-1.5 text-label leading-[1.6] text-ink-soft">
                Lấy token: mở Zalo, tìm OA &quot;Zalo Bot Manager&quot;, chọn &quot;Tạo bot&quot;
                (tên phải bắt đầu bằng &quot;Bot&quot;). Token được gửi vào tin nhắn Zalo cho bạn.
                Hệ thống sẽ kiểm token với Zalo trước khi lưu.
              </p>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-small font-medium text-ink">Agent (não)</label>
            <SelectMenu
              size="md"
              value={form.agentId}
              options={agentOptions}
              onChange={onAgent}
              ariaLabel="Agent (não)"
            />
          </div>

          {canPolicy && (
            <PolicyProfileSection
              value={form.policyProfile}
              initial={account?.policy_profile ?? HO_SO_MAC_DINH}
              onChange={onPolicy}
            />
          )}

          <div className="space-y-2 rounded-tile border border-line p-4">
            <div className={SECTION_TITLE}>Policies</div>
            <Toggle
              field="respondToGroups"
              value={form.respondToGroups}
              onChange={setBoolean}
              label="Trả lời trong nhóm"
            />
            <Toggle
              field="groupRequireMention"
              value={form.groupRequireMention}
              onChange={setBoolean}
              label="Nhóm phải @mention mới trả lời"
            />
            <Toggle
              field="groupPassiveListen"
              value={form.groupPassiveListen}
              onChange={setBoolean}
              label="Nghe passive trong nhóm"
              hint="Tin không @mention vẫn ghi vào ngữ cảnh, không tốn LLM"
            />
          </div>

          <div className="space-y-2 rounded-tile border border-line p-4">
            <div className={SECTION_TITLE}>Phản hồi tức thì</div>
            <Toggle
              field="typingIndicatorEnabled"
              value={form.typingIndicatorEnabled}
              onChange={setBoolean}
              label='Hiện "đang nhập" khi bot xử lý'
              hint="Giống người thật đang gõ, tự tắt khi gửi xong"
            />
            <ReactionSection
              form={form}
              reactionIcons={reactionIcons}
              onToggle={setBoolean}
              onPickIcon={onPickIcon}
            />
          </div>

          {form.channel === "zalo_personal" && (
            <div className="space-y-2 rounded-tile border border-line p-4">
              <div className={SECTION_TITLE}>Kết bạn</div>
              <Toggle
                field="autoAcceptFriends"
                value={form.autoAcceptFriends}
                onChange={setBoolean}
                label="Tự động chấp nhận yêu cầu kết bạn"
                hint="Bot tự accept sau khoảng chờ dưới đây. Tắt thì bạn tự duyệt ở tab Bạn bè."
              />
              {form.autoAcceptFriends && (
                <label className="flex items-center gap-2 pt-1 text-small text-ink-soft">
                  Chờ
                  <input
                    type="number"
                    min={0}
                    max={1440}
                    step={1}
                    value={form.autoAcceptFriendDelayMinutes}
                    onChange={(e) =>
                      // Math.round: server validate .int(), số thập phân -> 400.
                      setField(
                        "autoAcceptFriendDelayMinutes",
                        Math.max(0, Math.min(1440, Math.round(Number(e.target.value) || 0))),
                      )
                    }
                    className="w-20 rounded-control border border-line bg-surface px-2 py-1 text-ink max-sm:min-h-11"
                  />
                  phút rồi mới accept
                </label>
              )}
            </div>
          )}

          <div className="space-y-2 rounded-tile border border-line p-4">
            <div className={SECTION_TITLE}>Allowlist</div>
            <SelectMenu
              size="md"
              value={form.allowlistMode}
              options={ALLOWLIST_OPTIONS}
              onChange={onAllowlistMode}
              ariaLabel="Allowlist"
            />
            {form.allowlistMode === "list" && (
              <textarea
                className="gc-input min-h-24 w-full resize-y"
                value={form.allowlistIds}
                onChange={(e) => setField("allowlistIds", e.target.value)}
                placeholder={"Mỗi dòng 1 user ID\n1234567890123456789"}
              />
            )}
          </div>

          {form.channel === "zalo_oa" && (
            <p className="text-label leading-[1.6] text-ink-soft">{MO_TA_KENH_OA}</p>
          )}
          {error && <p className="text-small text-danger">{error}</p>}
        </div>

        <div className="border-t border-line px-5 py-4">
          <button
            onClick={save}
            disabled={busy || !form.label || (!account && !form.id)}
            className="min-h-11 w-full rounded-control bg-brand-500 py-2.5 text-body font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {busy ? "Đang lưu..." : account ? "Lưu thay đổi" : "Tạo account"}
          </button>
        </div>
      </div>
    </div>
  );
}
