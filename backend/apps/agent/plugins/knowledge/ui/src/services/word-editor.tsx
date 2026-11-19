/** A list of short words as chips with a box to add more (type + Enter) and an x to remove: aliases, branches. */
import { type KeyboardEvent, useState } from "react";

import { Chip } from "../parts";
import { ui } from "../sdk";
import { addWords, removeWord } from "./services-logic";

export function WordEditor({
  label,
  words,
  placeholder,
  disabled = false,
  onChange,
}: {
  label: string;
  words: readonly string[];
  placeholder: string;
  disabled?: boolean;
  /** Called with the new list as soon as a word is added or removed. */
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const next = addWords(words, draft);
    setDraft("");
    if (next.length !== words.length) onChange(next);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    commit();
  }

  return (
    <div className="space-y-2">
      {words.length > 0 && (
        <ul aria-label={label} className="flex flex-wrap gap-1.5">
          {words.map((word) => (
            <li key={word}>
              <Chip onRemove={disabled ? undefined : () => onChange(removeWord(words, word))}>{word}</Chip>
            </li>
          ))}
        </ul>
      )}
      <ui.Input
        aria-label={`Thêm ${label.toLowerCase()}`}
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
      />
    </div>
  );
}
