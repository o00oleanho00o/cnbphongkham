package com.pema.clinic.shared.finance

/** Commands throw with the server's error message when rejected. */
interface FinanceRepository {
    /** Role-scoped finance projection for [month] (`yyyy-MM`). */
    suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot

    suspend fun approveEntry(id: String, actor: FinanceActor)

    suspend fun voidEntry(id: String, reason: String, actor: FinanceActor)

    suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor)

    /** [key] makes retries idempotent on the server. */
    suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor)

    suspend fun closePeriod(month: String, actor: FinanceActor)

    suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor)

    /** [rate] in basis points; [basis] is `net`, `list` or `collected`. */
    suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor)

    suspend fun markNotificationRead(id: String, actor: FinanceActor)
}
