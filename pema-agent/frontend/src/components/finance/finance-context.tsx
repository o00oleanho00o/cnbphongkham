"use client";

// What every finance page needs from the shell: the month and the projection of the address (`?month=`,
// `?scope=own`), who may write, and a counter that "Làm mới" and every change raise so the pages load again.
import { createContext, useContext } from "react";

import type { FinanceScope } from "@/lib/finance/finance-view";

export type FinanceContextValue = {
  month: string;
  scope: FinanceScope;
  /** `finance.write` and the clinic projection: records, approves, voids, closes and pays. */
  canWrite: boolean;
  /** `finance.collect`: raises the invoice of an order and records receipts. */
  canCollect: boolean;
  isOwner: boolean;
  /** Changes with every reload; a page puts it in the dependencies of its load. */
  refreshKey: number;
  reload: () => void;
};

export const FinanceContext = createContext<FinanceContextValue | null>(null);

export function useFinance(): FinanceContextValue {
  const value = useContext(FinanceContext);
  if (!value) throw new Error("useFinance must be used inside the finance layout");
  return value;
}
