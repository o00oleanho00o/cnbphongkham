"use client";

// Small data-loading hook for the clinic screens. It keeps the last good data while a reload runs
// (no flash of an empty list when a filter changes), ignores answers of requests that are no longer the
// latest, and exposes `reload` for "after I changed something" refreshes.
import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "@/lib/api/client";

export type LoadState<T> = {
  data: T | undefined;
  error: string;
  loading: boolean;
  reload: () => void;
  /** Replace the data locally (optimistic update after a successful mutation). */
  setData: (next: T) => void;
};

/**
 * `load` must be stable (wrap it in `useCallback` with the filters as dependencies): a new function
 * identity means "the inputs changed, fetch again".
 */
export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>): LoadState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const run = latest.current + 1;
    latest.current = run;
    const controller = new AbortController();
    setLoading(true);
    load(controller.signal)
      .then((value) => {
        if (latest.current !== run) return;
        setData(value);
        setError("");
      })
      .catch((e: unknown) => {
        if (latest.current !== run || controller.signal.aborted) return;
        setError(errorMessage(e));
      })
      .finally(() => {
        if (latest.current === run) setLoading(false);
      });
    return () => controller.abort();
  }, [load, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}
