/** Create or change an account: its kind (at creation only), credentials, who it answers and how it behaves. */
import { useEffect, useState } from "react";

import { agentTools, messageOf, zalo } from "../client";
import {
  type AccountForm,
  CHANNEL_HINT,
  CHANNEL_LABEL,
  EMPTY_OA_KEYS,
  PERSONAL_RISK,
  clampDelay,
  formOf,
  formProblem,
  oaKeysState,
  parseIds,
  patchOf,
  withChannel,
} from "../logic";
import { Drawer, Section, Switch } from "../parts";
import { ui } from "../sdk";
import type { Account, ChannelKind, OaKeys, ReactionIcon } from "../types";

const CHANNELS: readonly ChannelKind[] = ["zalo_personal", "zalo_bot", "zalo_oa"];

const OA_FIELDS: readonly { key: keyof OaKeys; label: string }[] = [
  { key: "app_id", label: "App ID" },
  { key: "app_secret", label: "App secret" },
  { key: "oa_secret_key", label: "OA secret key (kiểm chữ ký webhook)" },
  { key: "refresh_token", label: "Refresh token (OAuth v4)" },
];

export function AccountDrawer({
  account,
  onClose,
  onSaved,
}: {
  account: Account | null;
  onClose: () => void;
  onSaved: (saved: Account, created: boolean) => void;
}) {
  const [form, setForm] = useState<AccountForm>(() => formOf(account));
  const [botToken, setBotToken] = useState("");
  const [oaKeys, setOaKeys] = useState<OaKeys>(EMPTY_OA_KEYS);
  /** Created in this drawer already: a failed token step must not create it a second time (409). */
  const [created, setCreated] = useState<string | null>(null);
  const [icons, setIcons] = useState<ReactionIcon[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    zalo.reactionIcons().then(setIcons, () => setIcons([]));
    agentTools().then(setTools, () => setTools([]));
  }, []);

  function set<K extends keyof AccountForm>(key: K, value: AccountForm[K]) {
    setForm((before) => ({ ...before, [key]: value }));
  }

  async function save() {
    const creating = account === null && created === null;
    const problem =
      formProblem(form, creating) ??
      (form.channel === "zalo_oa" && oaKeysState(oaKeys) === "partial" ? "Nhập đủ bốn khóa OA, hoặc để trống cả bốn." : null);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError("");
    const id = account?.id ?? created ?? form.id;
    try {
      if (creating) {
        await zalo.create({ id: form.id, label: form.label.trim(), channel: form.channel });
        setCreated(form.id);
      }
      let saved = await zalo.update(id, patchOf(form));
      // Credentials last, on their own route: Zalo checks a bot token before it is stored.
      if (form.channel === "zalo_bot" && botToken.trim()) saved = await zalo.setBotToken(id, botToken.trim());
      if (form.channel === "zalo_oa" && oaKeysState(oaKeys) === "complete") saved = await zalo.setOaKeys(id, oaKeys);
      onSaved(saved, account === null);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  const listIds = parseIds(form.allowlistIds);
  const unknownTools = form.disabledTools.filter((t) => !tools.includes(t));

  return (
    <Drawer
      title={account ? `Sửa: ${account.label}` : "Thêm tài khoản Zalo"}
      onClose={onClose}
      footer={
        <ui.Button className="w-full" busy={busy} onClick={() => void save()}>
          {account ? "Lưu thay đổi" : "Tạo tài khoản"}
        </ui.Button>
      }
    >
      {account === null && (
        <>
          <ui.Field label="ID" hint="Chữ thường, số, gạch ngang; không đổi được sau khi tạo.">
            <ui.Input
              value={form.id}
              disabled={created !== null}
              placeholder="vd: nick-cham-soc"
              onChange={(e) => set("id", e.target.value.trim())}
            />
          </ui.Field>
          <ui.Field label="Loại kênh" hint={`${CHANNEL_HINT[form.channel]} Chốt lúc tạo.`}>
            <ui.Select
              value={form.channel}
              disabled={created !== null}
              onChange={(e) => setForm(withChannel(form, e.target.value as ChannelKind))}
              options={CHANNELS.map((c) => ({ value: c, label: CHANNEL_LABEL[c] }))}
            />
          </ui.Field>
          {form.channel === "zalo_personal" && created === null && (
            <label className="flex items-start gap-2 rounded-tile border border-warning-line bg-warning-soft p-3 text-small text-ink">
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0"
                checked={form.riskAccepted}
                onChange={(e) => set("riskAccepted", e.target.checked)}
              />
              <span>{PERSONAL_RISK}</span>
            </label>
          )}
        </>
      )}

      <ui.Field label="Tên hiển thị">
        <ui.Input value={form.label} placeholder="vd: Nick chăm sóc khách hàng" onChange={(e) => set("label", e.target.value)} />
      </ui.Field>

      {form.channel === "zalo_bot" && (
        <ui.Field
          label={account?.has_credentials ? "Token bot (đã có - nhập mới để thay)" : "Token bot"}
          hint='Mở Zalo, tìm OA "Zalo Bot Manager", chọn "Tạo bot"; token được gửi vào tin nhắn. Zalo kiểm token trước khi lưu.'
        >
          <ui.Input
            type="password"
            autoComplete="off"
            className="font-mono"
            value={botToken}
            placeholder={account?.has_credentials ? "Để trống nếu không đổi" : "123456789:..."}
            onChange={(e) => setBotToken(e.target.value)}
          />
        </ui.Field>
      )}

      {form.channel === "zalo_oa" && (
        <Section title={account?.has_credentials ? "Khóa OA (đã có - nhập đủ bốn để thay)" : "Khóa OA"}>
          {OA_FIELDS.map(({ key, label }) => (
            <ui.Field key={key} label={label}>
              <ui.Input
                type={key === "app_id" ? "text" : "password"}
                autoComplete="off"
                value={oaKeys[key]}
                onChange={(e) => setOaKeys({ ...oaKeys, [key]: e.target.value })}
              />
            </ui.Field>
          ))}
          <p className="text-label text-ink-soft">{CHANNEL_HINT.zalo_oa}</p>
        </Section>
      )}

      <Section title="Người được trả lời">
        <ui.Select
          aria-label="Người được trả lời"
          value={form.allowlistMode}
          onChange={(e) => set("allowlistMode", e.target.value === "list" ? "list" : "all")}
          options={[
            { value: "all", label: "Trả lời tất cả mọi người" },
            { value: "list", label: "Chỉ trả lời user ID trong danh sách" },
          ]}
        />
        {form.allowlistMode === "list" && (
          <>
            <textarea
              aria-label="Danh sách user ID"
              className={`${ui.FIELD_CLASS} min-h-24 resize-y font-mono`}
              value={form.allowlistIds}
              placeholder={"Mỗi dòng một user ID\n1234567890123456789"}
              onChange={(e) => set("allowlistIds", e.target.value)}
            />
            <p className="text-label text-ink-soft">
              {listIds.length === 0
                ? "Danh sách trống: agent chưa trả lời ai. Người nhắn tới vẫn hiện ở trang Danh bạ, thêm họ từ đó."
                : `${listIds.length} người. Thêm hoặc bỏ nhanh ở trang Danh bạ.`}
            </p>
          </>
        )}
      </Section>

      <Section title="Nhóm">
        <Switch label="Trả lời trong nhóm" checked={form.respondToGroups} onChange={(v) => set("respondToGroups", v)} />
        <Switch
          label="Nhóm phải @nhắc tên mới trả lời"
          checked={form.groupRequireMention}
          onChange={(v) => set("groupRequireMention", v)}
        />
        <Switch
          label="Nghe tin nhóm không nhắc tên"
          hint="Ghi vào ngữ cảnh, không gọi model"
          checked={form.groupPassiveListen}
          onChange={(v) => set("groupPassiveListen", v)}
        />
      </Section>

      <Section title="Phản hồi tức thì">
        <Switch
          label='Hiện "đang nhập" khi agent xử lý'
          checked={form.typingIndicator}
          onChange={(v) => set("typingIndicator", v)}
        />
        {form.channel === "zalo_bot" ? (
          <p className="text-label text-ink-soft">Zalo Bot API không thả được cảm xúc, tài khoản bot bỏ qua mục này.</p>
        ) : (
          <>
            <Switch
              label="Thả cảm xúc khi nhận tin"
              hint="Báo người nhắn biết agent đã thấy tin"
              checked={form.autoReact}
              onChange={(v) => set("autoReact", v)}
            />
            {form.autoReact && (
              <div className="flex flex-wrap gap-1.5">
                {icons.map((icon) => (
                  <button
                    key={icon.key}
                    type="button"
                    title={icon.label}
                    aria-label={icon.label}
                    aria-pressed={form.autoReactIcon === icon.key}
                    onClick={() => set("autoReactIcon", icon.key)}
                    className={`flex h-11 w-11 items-center justify-center rounded-control border text-section sm:h-9 sm:w-9 ${
                      form.autoReactIcon === icon.key ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100" : "border-line hover:bg-tile"
                    }`}
                  >
                    {icon.emoji}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </Section>

      {form.channel === "zalo_personal" && (
        <Section title="Kết bạn">
          <Switch
            label="Tự chấp nhận lời mời kết bạn"
            hint="Tắt thì duyệt tay ở trang Bạn bè"
            checked={form.autoAcceptFriends}
            onChange={(v) => set("autoAcceptFriends", v)}
          />
          {form.autoAcceptFriends && (
            <label className="flex items-center gap-2 text-small text-ink-soft">
              Chờ
              <input
                type="number"
                min={0}
                max={1440}
                value={form.autoAcceptDelay}
                onChange={(e) => set("autoAcceptDelay", clampDelay(Number(e.target.value)))}
                className={`${ui.FIELD_CLASS} w-24!`}
              />
              phút rồi chấp nhận
            </label>
          )}
        </Section>
      )}

      {(tools.length > 0 || unknownTools.length > 0) && (
        <Section title="Tool dùng được">
          {[...tools, ...unknownTools].map((tool) => (
            <Switch
              key={tool}
              label={tool}
              hint={tools.includes(tool) ? undefined : "plugin của tool này đang tắt"}
              checked={!form.disabledTools.includes(tool)}
              onChange={(on) =>
                set("disabledTools", on ? form.disabledTools.filter((t) => t !== tool) : [...form.disabledTools, tool])
              }
            />
          ))}
        </Section>
      )}

      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
    </Drawer>
  );
}
