"use client";

// Small data-loading hook for the clinic screens. It keeps the last good data while a reload runs
// (no flash of an empty list when a filter changes), ignores answers of requests that are no longer the
// latest, and exposes `reload` for "after I changed something" refreshes.
//
// `refresh` is the quiet twin used by live updates (server events, the polling fallback): same request,
// but `loading` stays false, a failure keeps the data on screen instead of replacing it with an error, and
// nothing the person is doing (selection, scroll, a draft being typed) is touched, because only `data` changes.
import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "@/lib/api/client";

export type LoadState<T> = {
  data: T | undefined;
  error: string;
  loading: boolean;
  reload: () => void;
  /** Quiet reload for live updates: no loading state, errors keep the old data. */
  refresh: () => void;
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
  const counter = useRef(0);
  const quietTick = useRef(-1);
  const lastLoad = useRef(load);

  useEffect(() => {
    const run = latest.current + 1;
    latest.current = run;
    // Quiet only when this run was asked for by `refresh` and the inputs did not change meanwhile.
    const quiet = quietTick.current === tick && lastLoad.current === load;
    lastLoad.current = load;
    const controller = new AbortController();
    if (!quiet) setLoading(true);
    load(controller.signal)
      .then((value) => {
        if (latest.current !== run) return;
        setData(value);
        setError("");
      })
      .catch((e: unknown) => {
        if (latest.current !== run || controller.signal.aborted || quiet) return;
        setError(errorMessage(e));
      })
      .finally(() => {
        if (latest.current === run) setLoading(false);
      });
    return () => controller.abort();
  }, [load, tick]);

  const reload = useCallback(() => {
    counter.current += 1;
    setTick(counter.current);
  }, []);
  const refresh = useCallback(() => {
    counter.current += 1;
    quietTick.current = counter.current;
    setTick(counter.current);
  }, []);
  return { data, error, loading, reload, refresh, setData };
}
