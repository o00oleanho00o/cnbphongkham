/** "Cài đặt": which channels keep their conversations (all off until switched on), who on each is staff, and how
 * long messages are kept. */
import { useCallback, useEffect, useMemo, useState } from "react";

import { conversations, messageOf } from "../client";
import {
  NO_SETTINGS,
  RETENTION_OPTIONS,
  ROLE_LABEL,
  channelSetting,
  channelsToShow,
  retentionValue,
  sameSettings,
  toggled,
  withChannel,
} from "../logic";
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { ChannelSetting, Person, Settings } from "../types";

function People({
  channel,
  staff,
  onToggle,
}: {
  channel: string;
  staff: readonly string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    conversations
      .people(channel)
      .then((found) => setPeople(found.people))
      .catch((err: unknown) => {
        setError(messageOf(err));
        setPeople([]);
      });
  }, [channel]);

  return (
    <div className="space-y-2">
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {people === null && <ui.Empty>Đang tải…</ui.Empty>}
      {people !== null && people.length === 0 && !error && (
        <ui.Empty>Chưa có ai nhắn trong kênh này. Khi có tin, những người nhắn sẽ hiện ở đây.</ui.Empty>
      )}
      <ul className="space-y-1.5">
        {(people ?? []).map((person) => (
          <li
            key={person.sender_id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-tile border border-line px-3 py-2"
          >
            <span className="min-w-0 text-body text-ink">
              <span className="font-bold break-all text-heading">{person.name || person.sender_id}</span>
              <span className="ml-2 text-small text-ink-soft">
                {person.messages} tin · hiện tính là {ROLE_LABEL[person.role].toLowerCase()}
              </span>
            </span>
            <ui.Toggle
              checked={staff.includes(person.sender_id)}
              label={`${person.name || person.sender_id} là nhân viên`}
              onChange={(on) => onToggle(person.sender_id, on)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChannelCard({
  channel,
  setting,
  onChange,
}: {
  channel: string;
  setting: ChannelSetting;
  onChange: (next: ChannelSetting) => void;
}) {
  const [choosing, setChoosing] = useState(false);
  const [typed, setTyped] = useState("");
  const addable = typed.trim() !== "" && !setting.staff.includes(typed.trim());

  function addTyped() {
    if (!addable) return;
    onChange({ ...setting, staff: [...setting.staff, typed.trim()] });
    setTyped("");
  }

  return (
    <ui.Card
      title={channel}
      aside={
        <span className="flex items-center gap-2 text-small text-ink-soft">
          {setting.enabled ? "Đang lưu" : "Chưa lưu"}
          <ui.Toggle
            checked={setting.enabled}
            label={`Lưu hội thoại của kênh ${channel}`}
            onChange={(enabled) => onChange({ ...setting, enabled })}
          />
        </span>
      }
    >
      <div className="space-y-3">
        <p className="text-small text-ink-soft">
          Tin của chủ tài khoản gõ từ máy khác luôn tính là nhân viên. Thêm những người khác của phòng khám để tin của
          họ cũng tính là nhân viên, không lẫn với khách.
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-label text-ink-soft">Nhân viên:</span>
          {setting.staff.length === 0 && <span className="text-small text-ink-soft">chưa có ai</span>}
          {setting.staff.map((id) => (
            <Chip key={id} onRemove={() => onChange({ ...setting, staff: toggled(setting.staff, id, false) })}>
              {id}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <ui.Input
              aria-label="Mã người dùng của nhân viên"
              placeholder="Thêm theo mã người dùng"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
          <ui.Button variant="secondary" disabled={!addable} onClick={addTyped}>
            Thêm
          </ui.Button>
          <ui.Button variant="ghost" onClick={() => setChoosing((open) => !open)}>
            {choosing ? "Ẩn danh sách người nhắn" : "Chọn từ những người đã nhắn"}
          </ui.Button>
        </div>
        {choosing && (
          <People
            channel={channel}
            staff={setting.staff}
            onToggle={(id, on) => onChange({ ...setting, staff: toggled(setting.staff, id, on) })}
          />
        )}
      </div>
    </ui.Card>
  );
}

export function SettingsPage({ channels }: { channels: readonly string[] }) {
  const [saved, setSaved] = useState<Settings | null>(null);
  const [draft, setDraft] = useState<Settings>(NO_SETTINGS);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const found = await conversations.settings();
      setSaved(found);
      setDraft(found);
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = useMemo(() => channelsToShow(channels, draft), [channels, draft]);
  const changed = saved !== null && !sameSettings(saved, draft);

  async function save() {
    setBusy(true);
    setError("");
    setDone(false);
    try {
      const next = await conversations.saveSettings(draft);
      setSaved(next);
      setDraft(next);
      setDone(true);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Cài đặt lưu hội thoại"
        subtitle="Mặc định không kênh nào lưu. Bật từng kênh để lưu tin khách, tin nhân viên và câu trả lời của trợ lý."
        aside={
          <ui.Button busy={busy} disabled={!changed} onClick={() => void save()}>
            Lưu cài đặt
          </ui.Button>
        }
      />
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {done && !changed && <ui.Notice tone="success">Đã lưu.</ui.Notice>}
      {saved === null && !error && <p className="py-6 text-center text-small text-ink-soft">Đang tải…</p>}
      {saved !== null && (
        <ui.Card title="Thời hạn giữ">
          <div className="max-w-xs">
            <ui.Field label="Tin cũ hơn thời hạn này được xóa tự động" hint="Giữ mãi nếu không muốn xóa.">
              <ui.Select
                aria-label="Thời hạn giữ tin"
                value={retentionValue(draft.retention_days)}
                options={RETENTION_OPTIONS}
                onChange={(event) => setDraft({ ...draft, retention_days: Number(event.target.value) })}
              />
            </ui.Field>
          </div>
        </ui.Card>
      )}
      {saved !== null && shown.length === 0 && <ui.Empty>Chưa có kênh chat nào chạy.</ui.Empty>}
      {saved !== null &&
        shown.map((channel) => (
          <ChannelCard
            key={channel}
            channel={channel}
            setting={channelSetting(draft, channel)}
            onChange={(next) => setDraft((before) => withChannel(before, channel, next))}
          />
        ))}
    </div>
  );
}
