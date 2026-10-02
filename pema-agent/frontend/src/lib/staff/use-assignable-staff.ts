"use client";

// Staff a task or a conversation can be handed to (`GET /api/v1/staff/assignable`, every signed-in member may
// read it). While it loads, or when it cannot be read, the boxes still offer "Tôi" and "Giữ nguyên"; `reload`
// is the "Thử lại" of the error hint.
import { useCallback } from "react";

import {
  fetchAssignableStaff,
  invalidateAssignableStaff,
  type AssignableStaff,
} from "@/lib/staff/assignable-staff";
import { useLoad } from "@/lib/use-load";

const NONE: readonly AssignableStaff[] = [];

export function useAssignableStaff(): {
  staff: readonly AssignableStaff[];
  loading: boolean;
  error: string;
  reload: () => void;
} {
  const load = useCallback((signal: AbortSignal) => fetchAssignableStaff(signal), []);
  const { data, loading, error, reload } = useLoad(load);
  const retry = useCallback(() => {
    invalidateAssignableStaff();
    reload();
  }, [reload]);
  return { staff: data ?? NONE, loading, error, reload: retry };
}
