/** "Kỹ năng và quy tắc" of one account: the skills, rules and persona bound to it alone, the ones that reach it from
 * a wider place, what could be added, and the text its next question carries. The items themselves are written on
 * the Kỹ năng page; here they are only bound to the account or taken away from it. */
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { messageOf, skills } from "../client";
import {
  SKILL_KIND_LABEL,
  SKILL_STATUS_LABEL,
  accountScope,
  addableItems,
  ownItems,
  sharedItems,
  withAccount,
  withoutAccount,
} from "../logic";
import { Drawer, Section } from "../parts";
import { ui } from "../sdk";
import type { Account, SkillEffective, SkillItem } from "../types";

interface Loaded {
  items: SkillItem[];
  effective: SkillEffective;
}

function useLoaded(account: Account) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const [listing, effective] = await Promise.all([skills.items(), skills.effective(`zalo-${account.id}`)]);
      setLoaded({ items: listing.items, effective });
    } catch (err) {
      setError(messageOf(err));
    }
  }, [account.id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { loaded, error, reload };
}

function Line({ item, children }: { item: SkillItem; children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-tile border border-line px-3 py-2">
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-bold break-all text-heading">{item.name}</span>
          <ui.Badge>{SKILL_KIND_LABEL[item.kind]}</ui.Badge>
          {item.status !== "active" && <ui.Badge tone="warning">{SKILL_STATUS_LABEL[item.status]}</ui.Badge>}
        </span>
        <span className="block text-small text-ink-soft">{item.description}</span>
      </span>
      {children}
    </li>
  );
}

export function AccountSkills({ account, onClose }: { account: Account; onClose: () => void }) {
  const { loaded, error: loadError, reload } = useLoaded(account);
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showText, setShowText] = useState(false);

  async function change(item: SkillItem, scopes: string[], reason: string) {
    setBusy(true);
    setError("");
    try {
      await skills.setScopes(item.id, scopes, reason);
      setChosen("");
      await reload();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function addPicked() {
    if (!picked) return;
    await change(picked, withAccount(picked, account.id), `gắn cho tài khoản ${account.id}`);
  }

  const own = loaded ? ownItems(loaded.items, account.id) : [];
  const shared = loaded ? sharedItems(loaded.effective) : [];
  const addable = loaded ? addableItems(loaded.items, loaded.effective, account.id) : [];
  const picked = addable.find((item) => item.id === chosen);

  return (
    <Drawer
      title={`Kỹ năng và quy tắc: ${account.label}`}
      onClose={onClose}
      footer={
        <p className="text-label text-ink-soft">
          Viết hoặc sửa nội dung ở trang Kỹ năng. Ở đây chỉ chọn mục nào áp dụng cho riêng tài khoản này (
          {accountScope(account.id)}).
        </p>
      }
    >
      {loadError && <ui.Notice tone="danger">{loadError}</ui.Notice>}
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {!loaded && !loadError && <ui.Empty>Đang tải…</ui.Empty>}
      {loaded && (
        <>
          <Section title="Chỉ dành cho tài khoản này">
            {own.length === 0 && <p className="text-small text-ink-soft">Chưa có mục nào gắn riêng cho tài khoản này.</p>}
            <ul className="space-y-2">
              {own.map((item) => {
                const left = withoutAccount(item, account.id);
                return (
                  <Line key={item.id} item={item}>
                    {left ? (
                      <ui.Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void change(item, left, `bỏ khỏi tài khoản ${account.id}`)}
                      >
                        Bỏ khỏi tài khoản
                      </ui.Button>
                    ) : (
                      <span className="text-label text-ink-soft">Chỉ áp dụng cho tài khoản này: cất mục ở trang Kỹ năng</span>
                    )}
                  </Line>
                );
              })}
            </ul>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <ui.Select
                  aria-label="Mục thêm cho tài khoản này"
                  value={chosen}
                  onChange={(event) => setChosen(event.target.value)}
                  options={[
                    {
                      value: "",
                      label: addable.length === 0 ? "Không còn mục nào để thêm" : "Chọn mục để thêm",
                    },
                    ...addable.map((item) => ({
                      value: item.id,
                      label: `${item.name} (${SKILL_KIND_LABEL[item.kind]})`,
                    })),
                  ]}
                />
              </div>
              <ui.Button
                variant="secondary"
                busy={busy}
                disabled={!picked}
                onClick={() => void addPicked()}
              >
                Thêm
              </ui.Button>
            </div>
          </Section>

          <Section title="Áp dụng từ nơi rộng hơn">
            {shared.length === 0 && <p className="text-small text-ink-soft">Chưa có mục nào áp dụng chung cho tài khoản này.</p>}
            <ol className="space-y-1.5">
              {shared.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center gap-2 text-small text-ink">
                  <span className="font-bold break-all text-heading">{item.name}</span>
                  <ui.Badge>{SKILL_KIND_LABEL[item.kind]}</ui.Badge>
                  <ui.Badge tone="info">{item.rank === 0 ? "Cả agent" : "Mọi tài khoản Zalo"}</ui.Badge>
                </li>
              ))}
            </ol>
          </Section>

          <Section title="Văn bản trợ lý nhận ở mỗi câu hỏi">
            <ui.Button variant="secondary" onClick={() => setShowText((open) => !open)}>
              {showText ? "Ẩn" : "Xem"}
            </ui.Button>
            {showText && !loaded.effective.text && <p className="text-small text-ink-soft">Chưa có gì được thêm vào câu hỏi.</p>}
            {showText && loaded.effective.text && (
              <pre className="max-h-96 overflow-auto rounded-tile border border-line bg-tile p-3 text-small whitespace-pre-wrap text-ink">
                {loaded.effective.text}
              </pre>
            )}
          </Section>
        </>
      )}
    </Drawer>
  );
}
