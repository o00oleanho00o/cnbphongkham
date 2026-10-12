/** Loads the list of sources and keeps it fresh while some source is still being read. */
import { useCallback, useEffect, useRef, useState } from "react";

import { knowledge, messageOf } from "../client";
import type { SourceList, SourceQuery } from "../types";
import { REFRESH_MS, needsRefresh } from "./sources-logic";

export function useSourceList(query: SourceQuery) {
  const [list, setList] = useState<SourceList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const queryRef = useRef(query);
  queryRef.current = query;
  const latest = useRef(0);
  const inFlight = useRef(false);
  const key = JSON.stringify(query);

  /** `silent` reloads (the timer) keep the old list on screen and ignore a failure. */
  const load = useCallback(async (silent = false) => {
    latest.current += 1;
    const mine = latest.current;
    inFlight.current = true;
    if (!silent) setLoading(true);
    try {
      const next = await knowledge.sources(queryRef.current);
      if (mine !== latest.current) return;
      setList(next);
      setError("");
    } catch (err) {
      if (mine !== latest.current || silent) return;
      setError(messageOf(err));
    } finally {
      if (mine === latest.current) {
        inFlight.current = false;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    // A new query (filter, page) reloads; `load` itself reads the latest query from the ref.
  }, [key, load]);

  const polling = needsRefresh(list);
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      if (document.hidden || inFlight.current) return;
      void load(true);
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  return { list, error, loading, polling, reload: load };
}
