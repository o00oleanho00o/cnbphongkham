package com.pema.clinic.shared.finance

class FinanceRepositoryImpl(private val remote: FinanceRemoteDataSource) : FinanceRepository {
    private suspend fun send(action: String, body: Map<String, Any?>, actor: FinanceActor) =
        remote.postCommand(action, body, role = actor.role, doctor = actor.doctor)

    override suspend fun getState(month: String, actor: FinanceActor): FinanceSnapshot =
        FinanceMapper.snapshot(remote.fetchState(month = month, role = actor.role, doctor = actor.doctor))

    override suspend fun approveEntry(id: String, actor: FinanceActor) =
        send("approve", mapOf("id" to id), actor)

    override suspend fun voidEntry(id: String, reason: String, actor: FinanceActor) =
        send("void", mapOf("id" to id, "reason" to reason), actor)

    override suspend fun recordEntry(entry: ProcedureEntry, actor: FinanceActor) =
        send("entry", FinanceMapper.entry(entry), actor)

    override suspend fun recordPayment(key: String, invoice: String, amount: Int, method: String, actor: FinanceActor) =
        send("payment", mapOf("id" to key, "invoice" to invoice, "amount" to amount, "method" to method), actor)

    override suspend fun closePeriod(month: String, actor: FinanceActor) =
        send("close", mapOf("month" to month), actor)

    override suspend fun markPeriodPaid(month: String, reference: String, actor: FinanceActor) =
        send("paid", mapOf("month" to month, "reference" to reference), actor)

    override suspend fun updateRate(service: String, rate: Int, basis: String, actor: FinanceActor) =
        send("rate", mapOf("service" to service, "rate" to rate, "basis" to basis), actor)

    override suspend fun markNotificationRead(id: String, actor: FinanceActor) =
        send("read", mapOf("id" to id), actor)
}
