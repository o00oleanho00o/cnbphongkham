"use client";

// The clinic identities (`GET /api/v1/identities`, every operator may read): the Inbox filters by them and shows
// the one a thread runs on, the roster has a tab for each, the accounts page shows their limits. A failure is not
// an error screen: without identities the Inbox simply shows no identity name, so `error` is only a hint.
import { useCallback } from "react";

import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { useLoad } from "@/lib/use-load";

type Identity = Schemas["IdentityOut"];

const NONE: readonly Identity[] = [];

export function useIdentities(): {
  identities: readonly Identity[];
  loading: boolean;
  error: string;
  reload: () => void;
} {
  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/identities", { signal })),
    [],
  );
  const { data, loading, error, reload } = useLoad(load);
  return { identities: data ?? NONE, loading, error, reload };
}
