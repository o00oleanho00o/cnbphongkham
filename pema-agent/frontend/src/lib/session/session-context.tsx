"use client";

// Session of the signed-in staff member. The BE owns authentication (httpOnly cookie) and
// authorization; `permissions` from `GET /api/v1/me` only decide which menu entries are SHOWN. Every
// request is still checked by the BE, so a hidden entry is a convenience and never a security control.
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { http, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api";

export type Permission = Schemas["Permission"];
export type UserSummary = Schemas["UserSummary"];

type SessionValue = {
  user: UserSummary;
  permissions: ReadonlySet<Permission>;
  can: (permission: Permission) => boolean;
  canAny: (permissions: readonly Permission[]) => boolean;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({
  user,
  permissions,
  onLoggedOut,
  children,
}: {
  user: UserSummary;
  permissions: readonly Permission[];
  onLoggedOut: () => void;
  children: ReactNode;
}) {
  const set = useMemo(() => new Set<Permission>(permissions), [permissions]);
  const can = useCallback((p: Permission) => set.has(p), [set]);
  const canAny = useCallback((ps: readonly Permission[]) => ps.some((p) => set.has(p)), [set]);
  const logout = useCallback(async () => {
    await unwrap(http.POST("/api/v1/auth/logout")).catch(() => undefined);
    onLoggedOut();
  }, [onLoggedOut]);

  const value = useMemo<SessionValue>(
    () => ({ user, permissions: set, can, canAny, logout }),
    [user, set, can, canAny, logout],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside the signed-in shell");
  return ctx;
}

/** Vietnamese label of each role, for the user chip. */
export const ROLE_LABEL: Record<Schemas["Role"], string> = {
  owner: "Chủ phòng khám",
  manager: "Quản lý",
  doctor: "Bác sĩ",
  cs_staff: "CSKH",
  reception: "Lễ tân",
  patient: "Bệnh nhân",
};
