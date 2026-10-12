/** Runs one change at a time and keeps its error sentence, so every button of a screen shares one busy flag. */
import { useCallback, useState } from "react";

import { messageOf } from "../client";

export function useAction(): {
  /** The name of the running action, or "". */
  busy: string;
  error: string;
  /** Runs `work`; true when it finished without an error. */
  run: (name: string, work: () => Promise<unknown>) => Promise<boolean>;
  clearError: () => void;
} {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const run = useCallback(async (name: string, work: () => Promise<unknown>) => {
    setBusy(name);
    setError("");
    try {
      await work();
      return true;
    } catch (err) {
      setError(messageOf(err));
      return false;
    } finally {
      setBusy("");
    }
  }, []);

  const clearError = useCallback(() => setError(""), []);
  return { busy, error, run, clearError };
}
