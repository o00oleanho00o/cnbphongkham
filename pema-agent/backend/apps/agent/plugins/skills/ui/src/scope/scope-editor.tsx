/** Changes only where an item applies (not its text): the picker and a button that saves the places as a new version. */
import { useState } from "react";

import { messageOf, skills } from "../client";
import { ui } from "../sdk";
import type { Choices, Item } from "../types";
import { ScopePicker } from "./scope-picker";

function sameScopes(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((scope) => b.includes(scope));
}

export function ScopeEditor({
  item,
  choices,
  onSaved,
}: {
  item: Item;
  choices: Choices;
  onSaved: (item: Item) => void;
}) {
  const [scopes, setScopes] = useState<string[]>(item.scopes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed = !sameScopes(scopes, item.scopes);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const saved = await skills.update(item.id, { scopes, reason: "đổi nơi áp dụng" });
      onSaved(saved.item);
      setScopes(saved.item.scopes);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <ScopePicker scopes={scopes} choices={choices} onChange={setScopes} />
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {changed && (
        <div className="flex justify-end">
          <ui.Button busy={busy} onClick={() => void save()}>
            Lưu nơi áp dụng
          </ui.Button>
        </div>
      )}
    </div>
  );
}
