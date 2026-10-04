"use client";

// Accounts shared by the admin pages (the original passed `accounts` down as a prop from
// `DashboardShell`). The shell fills it once; a page that changes accounts calls `reload()`.
import { createContext, useContext, type ReactNode } from "react";

import type { AccountInfo } from "./account-info";

type AccountsValue = { accounts: AccountInfo[]; reload: () => void };

const AccountsContext = createContext<AccountsValue>({ accounts: [], reload: () => undefined });

export function AccountsProvider({
  value,
  children,
}: {
  value: AccountsValue;
  children: ReactNode;
}) {
  return <AccountsContext.Provider value={value}>{children}</AccountsContext.Provider>;
}

export function useAdminAccounts(): AccountsValue {
  return useContext(AccountsContext);
}
