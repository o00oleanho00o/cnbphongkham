/** Loads one source and keeps it fresh: reloads on demand and every 2 seconds while it is being processed. */
import { useCallback, useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import type { Source } from "../types";
import { statusOf } from "./detail-logic";

const REFRESH_MS = 2000;

export type SourceState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; source: Source };

export function isWorking(source: Source): boolean {
  return source.processing === "queued" || source.processing === "processing";
}

export function useSource(id: string): {
  state: SourceState;
  reload: () => void;
  replace: (source: Source) => void;
} {
  const [state, setState] = useState<SourceState>({ kind: "loading" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let stale = false;
    knowledge.source(id).then(
      (source) => {
        if (stale) return;
        setState({ kind: "ready", source });
      },
      (err: unknown) => {
        if (stale) return;
        setState(statusOf(err) === 404 ? { kind: "missing" } : { kind: "error", message: messageOf(err) });
      },
    );
    return () => {
      stale = true;
    };
  }, [id, tick]);

  const working = state.kind === "ready" && isWorking(state.source);
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => setTick((current) => current + 1), REFRESH_MS);
    return () => clearInterval(timer);
  }, [working]);

  const reload = useCallback(() => setTick((current) => current + 1), []);
  const replace = useCallback((source: Source) => setState({ kind: "ready", source }), []);
  return { state, reload, replace };
}

/** Changes when the content of a source does, not on every poll: tabs load their lists again when it does. */
export function contentKey(source: Source): string {
  return `${source.updated_at}|${source.processing}|${source.chunk_count}`;
}
