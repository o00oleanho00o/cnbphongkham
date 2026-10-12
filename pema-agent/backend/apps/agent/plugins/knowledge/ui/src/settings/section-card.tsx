/** One settings section: its title, where its values come from, its own save button and the result of the save. */
import { type FormEvent, type ReactNode, useState } from "react";

import { messageOf } from "../client";
import { ui } from "../sdk";
import type { KnowledgeSettings, SettingOrigin } from "../types";
import { ORIGIN_HINT, ORIGIN_LABEL } from "./settings-logic";

export interface Message {
  tone: "success" | "danger" | "info";
  text: string;
}

/** Runs a call for a section: `busy` while it waits, `message` after it (the server's sentence when it fails). */
export function useSectionRun() {
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<Message | null>(null);

  async function run(name: string, work: () => Promise<Message | null>) {
    setBusy(name);
    setMessage(null);
    try {
      setMessage(await work());
    } catch (err) {
      setMessage({ tone: "danger", text: messageOf(err) });
    } finally {
      setBusy("");
    }
  }

  return { busy, message, setMessage, run };
}

export interface SectionProps {
  settings: KnowledgeSettings;
  /** Takes the whole settings the server answered after a save. */
  onSaved: (next: KnowledgeSettings) => void;
}

export function SectionCard({
  title,
  intro,
  origin,
  onReset,
  resetBusy = false,
  saveDisabled,
  saveBusy,
  onSave,
  message,
  children,
}: {
  title: string;
  intro?: string;
  /** Where the values come from; leave out for a section that has no such thing. */
  origin?: SettingOrigin;
  /** Offered only when the values were saved here. */
  onReset?: () => void;
  resetBusy?: boolean;
  saveDisabled: boolean;
  saveBusy: boolean;
  onSave: () => void;
  message: Message | null;
  children: ReactNode;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSave();
  }

  return (
    <ui.Card
      title={title}
      aside={
        origin && (
          <span className="flex items-center gap-2">
            <span title={ORIGIN_HINT[origin]}>
              <ui.Badge tone={origin === "saved" ? "success" : "neutral"}>{ORIGIN_LABEL[origin]}</ui.Badge>
            </span>
            {origin === "saved" && onReset && (
              <ui.Button variant="ghost" busy={resetBusy} aria-label={`Về mặc định: ${title}`} onClick={onReset}>
                Về mặc định
              </ui.Button>
            )}
          </span>
        )
      }
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {intro && <p className="text-small text-ink-soft">{intro}</p>}
        {children}
        {message && <ui.Notice tone={message.tone}>{message.text}</ui.Notice>}
        <div>
          <ui.Button type="submit" busy={saveBusy} disabled={saveDisabled}>
            {`Lưu ${title.toLowerCase()}`}
          </ui.Button>
        </div>
      </form>
    </ui.Card>
  );
}
