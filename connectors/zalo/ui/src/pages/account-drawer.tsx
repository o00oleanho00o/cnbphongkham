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
  groupItems,
  type Item,
  personItems,
  oaKeysState,
  patchOf,
  toggledIds,
  withChannel,
} from "../logic";
import { PagedSwitches } from "../paged-switches";
import { Drawer, Section, Switch } from "../parts";
import { ui } from "../sdk";
import type { Account, ChannelKind, Contact, Friend, Group, OaKeys, ReactionIcon } from "../types";

/** The people a form lists: the most recent ones who wrote to the account (the Danh bạ page pages through all). */
const PEOPLE_SHOWN = 200;

/** Above this many people the form offers a search box. */
const SEARCH_FROM = 10;

const GROUP_HINTS = {
  unsaved: "Tạo tài khoản và đăng nhập trước. Nhóm nào nhắn tới sẽ hiện ở đây để bạn bật; nhóm mới mặc định tắt.",
  empty: "Chưa thấy nhóm nào. Một nhóm hiện ở đây sau tin nhắn đầu tiên của nhóm đó; nhóm mới mặc định tắt.",
};

const PEOPLE_HINTS = {
  unsaved: "Tạo tài khoản và đăng nhập trước. Ai nhắn tới sẽ hiện ở đây để bạn bật; người mới mặc định tắt.",
  empty: "Chưa có ai nhắn tới. Một người hiện ở đây sau tin nhắn đầu tiên của họ; người mới mặc định tắt.",
};

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
  const [groups, setGroups] = useState<Group[]>([]);
  const [people, setPeople] = useState<Contact[]>([]);
  const [friends, setFriends] = useState<Friend[]>([]);
  const [peopleQuery, setPeopleQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    zalo.reactionIcons().then(setIcons, () => setIcons([]));
    agentTools().then(setTools, () => setTools([]));
  }, []);

  const accountId = account?.id;
  useEffect(() => {
    if (accountId === undefined) return;
    zalo.groups(accountId).then(setGroups, () => setGroups([]));
    zalo.contacts({ account_id: accountId, limit: PEOPLE_SHOWN, offset: 0 }).then(setPeople, () => setPeople([]));
  }, [accountId]);

  // The friends of a personal nick come from Zalo itself: a nick that is not running has none to offer yet.
  const isPersonal = account?.channel === "zalo_personal";
  useEffect(() => {
    if (accountId === undefined || !isPersonal) return;
    zalo.friends(accountId).then(setFriends, () => setFriends([]));
  }, [accountId, isPersonal]);

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

  // The lists are cut from what the account had when the form opened, so a switch turned off stays in its place.
  const peopleItems = personItems(people, account?.allowlist.user_ids ?? [], friends);
  const groupItemsOf = (listed: readonly string[]) => groupItems(groups, listed);
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
            {peopleItems.length > SEARCH_FROM && (
              <input
                type="search"
                aria-label="Tìm người theo tên hoặc ID"
                placeholder="Tìm theo tên hoặc ID"
                className={ui.FIELD_CLASS}
                value={peopleQuery}
                onChange={(e) => setPeopleQuery(e.target.value)}
              />
            )}
            <ChoiceSwitches
              explain="Chỉ người được bật mới được agent trả lời trong chat 1-1. Gồm người đã nhắn tới và bạn bè của nick. Bật xong bấm Lưu thay đổi."
              hints={PEOPLE_HINTS}
              saved={account !== null}
              scope={`people:${accountId ?? ""}`}
              label="Người được trả lời"
              items={peopleItems}
              chosen={form.allowlistUserIds}
              query={peopleQuery}
              noMatch={`Không có ai khớp "${peopleQuery.trim()}".`}
              onChoose={(userId, on) => set("allowlistUserIds", toggledIds(form.allowlistUserIds, userId, on))}
            />
            {people.length >= PEOPLE_SHOWN && (
              <p className="text-label text-ink-soft">
                Chỉ lấy {PEOPLE_SHOWN} người nhắn gần nhất. Người nhắn cũ hơn bật ở trang Danh bạ.
              </p>
            )}
          </>
        )}
      </Section>

      <Section title="Nhóm">
        <Switch label="Trả lời trong nhóm" checked={form.respondToGroups} onChange={(v) => set("respondToGroups", v)} />
        {form.respondToGroups && (
          <>
            <ui.Select
              aria-label="Nhóm được trả lời"
              value={form.groupAllowlistMode}
              onChange={(e) => set("groupAllowlistMode", e.target.value === "list" ? "list" : "all")}
              options={[
                { value: "all", label: "Trả lời trong tất cả các nhóm" },
                { value: "list", label: "Chỉ trả lời trong nhóm thuộc danh sách" },
              ]}
            />
            {form.groupAllowlistMode === "list" && (
              <ChoiceSwitches
                title="Nhóm được trả lời"
                explain="Chỉ nhóm được bật mới được agent trả lời (ai trong nhóm cũng hỏi được, không xét danh sách người ở trên). Nhóm tắt: agent bỏ qua."
                hints={GROUP_HINTS}
                saved={account !== null}
                scope={`reply-groups:${accountId ?? ""}`}
                label="Nhóm được trả lời"
                items={groupItemsOf(account?.group_allowlist.group_ids ?? [])}
                chosen={form.groupAllowlistIds}
                noMatch="Chưa có nhóm nào."
                onChoose={(groupId, on) => set("groupAllowlistIds", toggledIds(form.groupAllowlistIds, groupId, on))}
              />
            )}
          </>
        )}
        <Switch
          label="Nhóm phải @nhắc tên mới trả lời"
          checked={form.groupRequireMention}
          onChange={(v) => set("groupRequireMention", v)}
        />
        <ChoiceSwitches
          title="Nhóm lắng nghe"
          explain="Chỉ nhóm được bật mới được ghi nhớ (mọi nội dung). Nhóm tắt: tin không được lưu, việc trả lời do mục trên quyết định."
          hints={GROUP_HINTS}
          saved={account !== null}
          scope={`listen-groups:${accountId ?? ""}`}
          label="Nhóm lắng nghe"
          items={groupItemsOf(account?.listen_group_ids ?? [])}
          chosen={form.listenGroupIds}
          noMatch="Chưa có nhóm nào."
          onChoose={(groupId, on) => set("listenGroupIds", toggledIds(form.listenGroupIds, groupId, on))}
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

/** A list of people or groups as switches in a short box; a line is on when its id is among the chosen. */
function ChoiceSwitches({
  title: heading,
  explain,
  hints,
  saved,
  scope,
  label,
  items,
  chosen,
  query,
  noMatch,
  onChoose,
}: {
  title?: string;
  explain: string;
  hints: { unsaved: string; empty: string };
  saved: boolean;
  scope: string;
  label: string;
  items: readonly Item[];
  chosen: readonly string[];
  query?: string;
  noMatch: string;
  onChoose: (id: string, on: boolean) => void;
}) {
  const title = heading && <p className="text-micro font-semibold tracking-wider text-ink-soft uppercase">{heading}</p>;
  if (!saved) {
    return (
      <>
        {title}
        <p className="text-label text-ink-soft">{hints.unsaved}</p>
      </>
    );
  }
  if (items.length === 0) {
    return (
      <>
        {title}
        <p className="text-label text-ink-soft">{hints.empty}</p>
      </>
    );
  }
  return (
    <>
      {title}
      <p className="text-label text-ink-soft">{explain}</p>
      <PagedSwitches scope={scope} items={items} chosen={chosen} query={query} label={label} noMatch={noMatch} onChoose={onChoose} />
    </>
  );
}
