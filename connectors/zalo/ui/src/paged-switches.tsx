/** A list of switches in a short box: five at first, five more each time the box is scrolled to its end. */
import { useRef } from "react";

import { type Item, matching } from "./logic";
import { PagingProvider, usePaged } from "./paging";
import { Switch } from "./parts";

interface PagedSwitchesProps {
  /** Tells this list from the others in the query cache (`people:<account>`, `groups:<account>`). */
  scope: string;
  items: readonly Item[];
  /** The ids that are on; read on every render, so a switch does not need the pages to be cut again. */
  chosen: readonly string[];
  query?: string;
  label: string;
  noMatch: string;
  onChoose: (id: string, on: boolean) => void;
}

export function PagedSwitches(props: PagedSwitchesProps) {
  return (
    <PagingProvider>
      <Pages {...props} />
    </PagingProvider>
  );
}

function Pages({ scope, items, chosen, query = "", label, noMatch, onChoose }: PagedSwitchesProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const { shown, loaded, hasNext, endRef } = usePaged(
    ["switches", scope, query.trim()],
    matching(items, query),
    boxRef,
  );

  if (loaded && shown.length === 0) return <p className="text-label text-ink-soft">{noMatch}</p>;
  const on = new Set(chosen);
  return (
    <div ref={boxRef} role="group" aria-label={label} tabIndex={0} className="max-h-56 space-y-3 overflow-y-auto pr-1">
      {shown.map((item) => (
        <Switch
          key={item.id}
          label={item.name}
          hint={item.id}
          checked={on.has(item.id)}
          onChange={(next) => onChoose(item.id, next)}
        />
      ))}
      {hasNext && (
        <div ref={endRef} className="py-1 text-center text-label text-ink-soft">
          Kéo xuống để xem thêm
        </div>
      )}
    </div>
  );
}
