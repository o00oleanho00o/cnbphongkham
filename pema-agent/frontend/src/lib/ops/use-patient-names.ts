"use client";

// Task and conversation DTOs carry the patient CODE only (data minimisation). Staff need a name to
// recognise the person, so the screens read the patient list ONCE (one request, never one per row) and
// look names up by id. Without `patient.read` the map stays empty and the screens show the code.
import { useEffect, useState } from "react";

import { http, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api";
import { useSession } from "@/lib/session/session-context";

export type PatientIndex = ReadonlyMap<string, Schemas["PatientOut"]>;

const EMPTY: PatientIndex = new Map();
const PAGE = 200;

export function usePatientIndex(): PatientIndex {
  const { can } = useSession();
  const allowed = can("patient.read");
  const [index, setIndex] = useState<PatientIndex>(EMPTY);

  useEffect(() => {
    if (!allowed) return;
    const controller = new AbortController();
    unwrap(
      http.GET("/api/v1/patients", {
        params: { query: { limit: PAGE } },
        signal: controller.signal,
      }),
    )
      .then((page) => setIndex(new Map(page.items.map((p) => [p.id, p]))))
      .catch(() => setIndex(EMPTY));
    return () => controller.abort();
  }, [allowed]);

  return index;
}

/** "Nguyễn Thu Hà" when known, otherwise the code. */
export function displayName(index: PatientIndex, id: string | null, code: string | null): string {
  const known = id ? index.get(id)?.full_name : undefined;
  return known ?? code ?? "Chưa gắn hồ sơ";
}
