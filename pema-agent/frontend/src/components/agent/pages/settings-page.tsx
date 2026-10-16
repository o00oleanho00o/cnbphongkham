"use client";

// Cài đặt của agent: time zone, the reply after a failed turn, the variables, the persona (Vai trò), the rules and
// the memory. Each field says where its value comes from (the stored one, or the profile's) and can go back to the
// profile; a save sends only what changed. A persona or rules text kept in the system hides the file in git, so the
// page warns and offers "Dùng lại file". Changes apply from the next reply of the agent.
import { useEffect, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import {
  SettingHead,
  TEXTAREA_CLASS,
  VariablesEditor,
} from "@/components/agent/pages/settings-fields";
import {
  Button,
  Card,
  Input,
  type KitTone,
  Notice,
  PageHeader,
  Toggle,
} from "@/components/agent/plugin-kit";
import { agentApi as api } from "@/lib/agent/api";
import {
  type AgentSettings,
  draftErrors,
  draftOf,
  isAgentSettings,
  isStored,
  patchOf,
  SETTINGS_PATH,
  type SettingField,
  type SettingsDraft,
  type SettingsPatch,
  takeFields,
} from "@/lib/agent/agent-settings";

type Message = { tone: KitTone; text: string };
type TextField = "persona" | "rules";

const STORED_TEXT_WARNING =
  "Đang dùng bản đã lưu trong hệ thống, không dùng file SOUL.md (hoặc AGENTS.md). Sửa file trong git sẽ không đổi agent cho tới khi bấm 'Dùng lại file'.";

const MEMORY_LABELS = {
  memory_agent_chars: "Trí nhớ về agent (số ký tự)",
  memory_user_chars: "Trí nhớ về khách (số ký tự)",
} as const;

const errorText = (err: unknown) => (err instanceof Error ? err.message : "Lỗi");

function accept(answer: unknown): AgentSettings {
  if (!isAgentSettings(answer)) throw new Error("Câu trả lời của agent không đúng dạng.");
  return answer;
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-1 text-label text-danger">
      {message}
    </p>
  );
}

export function SettingsPage() {
  const [shown, setShown] = useState<AgentSettings | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState("");
  const { confirm, confirmDialog } = useConfirmDialog();

  useEffect(() => {
    api
      .get<unknown>(SETTINGS_PATH)
      .then((answer) => {
        const loaded = accept(answer);
        setShown(loaded);
        setDraft(draftOf(loaded));
      })
      .catch((err: unknown) => setMessage({ tone: "danger", text: errorText(err) }));
  }, []);

  if (!shown || !draft) {
    return (
      <div>
        <PageHeader title="Cài đặt" />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    );
  }

  /** `fields`: which parts of the draft the answer replaces; the rest keeps what is being typed. */
  async function send(
    label: string,
    request: () => Promise<unknown>,
    fields: readonly SettingField[] | "all",
    success: string,
  ) {
    setBusy(label);
    setMessage(null);
    try {
      const fresh = accept(await request());
      setShown(fresh);
      setDraft((current) =>
        fields === "all" || !current ? draftOf(fresh) : takeFields(current, fresh, fields),
      );
      setMessage({ tone: "success", text: success });
    } catch (err) {
      setMessage({ tone: "danger", text: errorText(err) });
    } finally {
      setBusy("");
    }
  }

  const patch = (
    label: string,
    body: SettingsPatch,
    fields: readonly SettingField[],
    text: string,
  ) => send(label, () => api.patch(SETTINGS_PATH, body), fields, text);

  const toProfile = (field: SettingField, label: string) =>
    patch(`reset-${field}`, { [field]: null }, [field], `${label}: đã về mặc định của profile.`);

  async function backToFile(field: TextField, label: string) {
    const ok = await confirm({
      title: "Dùng lại file?",
      message: `Bản "${label}" đã lưu trong hệ thống sẽ bị bỏ; agent dùng lại nội dung của file từ lượt trả lời tiếp theo. Phần đang gõ trong ô này cũng mất.`,
      confirmLabel: "Dùng lại file",
      tone: "normal",
    });
    if (!ok) return;
    await patch(`file-${field}`, { [field]: null }, [field], `${label}: agent dùng lại file.`);
  }

  async function clearAll() {
    const ok = await confirm({
      title: "Xóa mọi cài đặt đã lưu?",
      message:
        "Mọi giá trị đã chỉnh ở trang này và các công cụ đã bật tắt tay bị bỏ: agent dùng lại cấu hình của profile. Không hoàn tác được.",
      confirmLabel: "Xóa cài đặt",
    });
    if (!ok) return;
    await send(
      "clear",
      () => api.del(SETTINGS_PATH),
      "all",
      "Đã xóa mọi cài đặt đã lưu: agent dùng lại cấu hình của profile.",
    );
  }

  const change = (next: Partial<SettingsDraft>) =>
    setDraft((current) => (current ? { ...current, ...next } : current));
  const errors = draftErrors(draft);
  const changes = patchOf(draft, shown);
  const nothingToSave = Object.keys(changes).length === 0 || Object.keys(errors).length > 0;

  const head = (field: SettingField, label: string, id?: string) => (
    <SettingHead
      htmlFor={id}
      label={label}
      stored={isStored(shown, field)}
      busy={busy === `reset-${field}`}
      onReset={() => toProfile(field, label)}
    />
  );

  const textCard = (field: TextField, title: string, label: string, hint: string) => (
    <Card title={title}>
      <div className="space-y-3">
        <p className="text-small text-ink-soft">{hint}</p>
        {isStored(shown, field) && (
          <Notice tone="warning">
            <p>{STORED_TEXT_WARNING}</p>
            <div className="mt-2">
              <Button
                variant="secondary"
                busy={busy === `file-${field}`}
                aria-label={`Dùng lại file: ${label}`}
                onClick={() => backToFile(field, label)}
              >
                Dùng lại file
              </Button>
            </div>
          </Notice>
        )}
        <div>
          <SettingHead htmlFor={`setting-${field}`} label={label} stored={isStored(shown, field)} />
          <textarea
            id={`setting-${field}`}
            className={TEXTAREA_CLASS}
            rows={10}
            maxLength={20000}
            value={draft[field]}
            onChange={(e) => change({ [field]: e.target.value })}
          />
        </div>
      </div>
    </Card>
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cài đặt"
        subtitle="Múi giờ, lời trả lời khi lỗi, biến, vai trò, quy tắc và trí nhớ của agent. Thay đổi áp dụng từ lượt trả lời tiếp theo của agent, không cần khởi động lại."
      />
      <Card title="Chung">
        <div className="space-y-4">
          <div>
            {head("timezone", "Múi giờ", "setting-timezone")}
            <Input
              id="setting-timezone"
              value={draft.timezone}
              maxLength={64}
              onChange={(e) => change({ timezone: e.target.value })}
            />
            <FieldError message={errors.timezone} />
            <p className="mt-1 text-label text-ink-soft">
              Tên múi giờ IANA, ví dụ Asia/Ho_Chi_Minh.
            </p>
          </div>
          <div>
            {head("failure_reply", "Lời trả lời khi lượt chat lỗi", "setting-failure_reply")}
            <textarea
              id="setting-failure_reply"
              className={TEXTAREA_CLASS}
              rows={3}
              maxLength={1000}
              value={draft.failure_reply}
              onChange={(e) => change({ failure_reply: e.target.value })}
            />
            <p className="mt-1 text-label text-ink-soft">
              Tin gửi cho khách khi agent không trả lời được một lượt.
            </p>
          </div>
        </div>
      </Card>
      <Card title="Biến">
        <div className="space-y-3">
          <p className="text-small text-ink-soft">
            Giá trị điền vào chỗ {"{{tên_biến}}"} trong Vai trò và Quy tắc. Biến chưa chỉnh lấy theo
            profile.
          </p>
          {head("variables", "Danh sách biến")}
          <VariablesEditor
            rows={draft.variables}
            stored={isStored(shown, "variables")}
            error={errors.variables}
            onChange={(rows) => change({ variables: rows })}
            onResetRow={(name) =>
              patch(
                `row-${name}`,
                { variables: { [name]: null } },
                ["variables"],
                `Biến ${name}: về giá trị của profile.`,
              )
            }
          />
        </div>
      </Card>
      {textCard(
        "persona",
        "Vai trò của agent",
        "Vai trò",
        "Agent là ai và nói chuyện thế nào; có thể dùng {{tên_biến}}.",
      )}
      {textCard(
        "rules",
        "Quy tắc của agent",
        "Quy tắc",
        "Những điều agent phải làm và không được làm; có thể dùng {{tên_biến}}.",
      )}
      <Card title="Bộ nhớ">
        <div className="space-y-4">
          <div>
            {head("memory_enabled", "Trí nhớ của agent")}
            <div className="flex items-center gap-2">
              <Toggle
                label="Bật trí nhớ"
                checked={draft.memory_enabled}
                onChange={(next) => change({ memory_enabled: next })}
              />
              <span className="text-body text-ink">
                {draft.memory_enabled ? "Đang bật" : "Đang tắt"}
              </span>
            </div>
          </div>
          {(["memory_agent_chars", "memory_user_chars"] as const).map((field) => (
            <div key={field}>
              {head(field, MEMORY_LABELS[field], `setting-${field}`)}
              <Input
                id={`setting-${field}`}
                type="number"
                inputMode="numeric"
                value={draft[field]}
                onChange={(e) => change({ [field]: e.target.value })}
              />
              <FieldError message={errors[field]} />
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <div className="space-y-3">
          {message && <Notice tone={message.tone}>{message.text}</Notice>}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              busy={busy === "save"}
              disabled={nothingToSave}
              onClick={() =>
                send(
                  "save",
                  () => api.patch(SETTINGS_PATH, changes),
                  "all",
                  "Đã lưu - áp dụng từ lượt trả lời tiếp theo.",
                )
              }
            >
              Lưu thay đổi
            </Button>
            <Button variant="ghost" disabled={busy !== ""} onClick={() => setDraft(draftOf(shown))}>
              Bỏ thay đổi chưa lưu
            </Button>
            <Button
              variant="danger"
              className="ml-auto"
              busy={busy === "clear"}
              disabled={!shown.stored}
              onClick={clearAll}
            >
              Xóa mọi cài đặt đã lưu
            </Button>
          </div>
          {shown.updated_by && (
            <p className="text-small text-ink-soft">Sửa lần cuối bởi {shown.updated_by}</p>
          )}
        </div>
      </Card>
      {confirmDialog}
    </div>
  );
}
