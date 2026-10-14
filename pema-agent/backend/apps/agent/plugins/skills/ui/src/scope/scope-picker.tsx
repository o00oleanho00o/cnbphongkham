/** Where an item applies: chips for the scopes it has, and a way to add the whole agent, a plugin or a channel. */
import { useState } from "react";

import { AGENT_SCOPE, scopeLabel, scopeOf, validScope } from "../logic";
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { Choices } from "../types";

const KIND_OPTIONS = [
  { value: "channel", label: "Một kênh (một tài khoản)" },
  { value: "plugin", label: "Mọi kênh của một plugin" },
  { value: AGENT_SCOPE, label: "Cả agent" },
] as const;

type AddKind = (typeof KIND_OPTIONS)[number]["value"];

function isAddKind(value: string): value is AddKind {
  return KIND_OPTIONS.some((option) => option.value === value);
}

function addedScope(kind: AddKind, key: string): string {
  if (kind === AGENT_SCOPE) return AGENT_SCOPE;
  return scopeOf(kind, key);
}

export function ScopePicker({
  scopes,
  choices,
  onChange,
}: {
  scopes: readonly string[];
  choices: Choices;
  onChange: (next: string[]) => void;
}) {
  const [kind, setKind] = useState<AddKind>("channel");
  const [key, setKey] = useState("");
  const candidate = addedScope(kind, key);
  const addable = validScope(candidate) && !scopes.includes(candidate);
  const options = kind === "plugin" ? choices.plugins : choices.channels;

  function add() {
    if (!addable) return;
    onChange([...scopes, candidate]);
    setKey("");
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {scopes.length === 0 && (
          <span className="text-small text-ink-soft">Chưa chọn nơi nào, nên áp dụng cho cả agent.</span>
        )}
        {scopes.map((scope) => (
          <Chip key={scope} onRemove={() => onChange(scopes.filter((other) => other !== scope))}>
            {scopeLabel(scope)}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <ui.Select
            aria-label="Loại nơi áp dụng"
            value={kind}
            options={KIND_OPTIONS}
            onChange={(event) => {
              if (isAddKind(event.target.value)) setKind(event.target.value);
            }}
          />
        </div>
        {kind !== AGENT_SCOPE && (
          <div className="min-w-48 flex-1">
            <ui.Input
              aria-label="Tên plugin hoặc kênh"
              list="skills-scope-options"
              placeholder={kind === "plugin" ? "ví dụ zalo" : "ví dụ zalo-123"}
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
            <datalist id="skills-scope-options">
              {options.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>
        )}
        <ui.Button variant="secondary" disabled={!addable} onClick={add}>
          Thêm nơi áp dụng
        </ui.Button>
      </div>
    </div>
  );
}
