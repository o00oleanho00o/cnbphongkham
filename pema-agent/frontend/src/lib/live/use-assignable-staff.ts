"use client";

// Staff a task or a conversation can be handed to (`GET /api/v1/staff/assignable`, every signed-in member may
// read it). While it loads, or when it cannot be read, the boxes still offer "Tôi" and "Giữ nguyên".
import { useCallback } from "react";

import { fetchAssignableStaff } from "@/lib/live/live-api";
import type { AssignableStaff } from "@/lib/live/live-types";
import { useLoad } from "@/lib/use-load";

const NONE: readonly AssignableStaff[] = [];

export function useAssignableStaff(): {
  staff: readonly AssignableStaff[];
  loading: boolean;
  error: string;
} {
  const load = useCallback((signal: AbortSignal) => fetchAssignableStaff(signal), []);
  const { data, loading, error } = useLoad(load);
  return { staff: data ?? NONE, loading, error };
}
