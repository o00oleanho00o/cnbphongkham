package com.pema.clinic.shared.finance

import androidx.compose.runtime.Immutable
import kotlin.time.Clock
import kotlin.time.ExperimentalTime
import kotlin.time.Instant
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

@Immutable
data class FinanceSummary(
    val revenue: Int,
    val fee: Int,
    val pending: Int,
    /** Omitted from a doctor's private projection. */
    val collected: Int? = null,
    val debt: Int? = null,
)

@Immutable
data class FinanceDoctor(val id: String, val name: String)

/** A billable procedure and its current fee policy. */
@Immutable
data class ProcedureService(
    val id: String,
    val name: String,
    val price: Int,
    /** Basis points: 2000 = 20%. */
    val rate: Int,
    /** `net`, `list` or `collected`. */
    val basis: String,
    val version: Int,
) {
    val ratePercent: Double get() = rate / 100.0
}

/** One performer's share of a completed procedure in the month. */
@Immutable
data class ProcedureRow(
    val id: String,
    val date: String,
    val patient: String,
    val service: String,
    val doctor: String,
    /** `pending`, `approved` or `void`. */
    val status: String,
    val base: Int,
    /** Basis points. */
    val rate: Int,
    val revenue: Int,
    val fee: Int,
) {
    val ratePercent: Double get() = rate / 100.0
    val isVoid: Boolean get() = status == "void"
    val isPending: Boolean get() = status == "pending"
}

@Immutable
data class FinanceInvoice(
    val id: String,
    val patient: String,
    /** `finance` or `web` (legacy cashier mirror). */
    val source: String,
    val amount: Int,
    val received: Int,
) {
    val due: Int get() = amount - received
}

@Immutable
data class PaymentNotification(
    val id: String,
    val title: String,
    val body: String,
    val read: Boolean,
    /** ISO-8601 with offset. */
    val at: String,
) {
    /** `2026-09-22T10:00:00+07:00` → `2026-09-22 10:00`. */
    val shortTime: String get() = at.substring(0, 16).replace('T', ' ')
}

/** Role-scoped finance projection for one month. */
@Immutable
data class FinanceSnapshot(
    val month: String,
    val today: String,
    /** `open`, `closed` or `paid`. */
    val periodStatus: String,
    val summary: FinanceSummary,
    val doctors: List<FinanceDoctor> = emptyList(),
    val services: List<ProcedureService> = emptyList(),
    val rows: List<ProcedureRow> = emptyList(),
    val invoices: List<FinanceInvoice> = emptyList(),
    val notifications: List<PaymentNotification> = emptyList(),
) {
    val periodOpen: Boolean get() = periodStatus == "open"
    val periodClosed: Boolean get() = periodStatus == "closed"

    val unread: Int get() = notifications.count { !it.read }

    fun doctorName(id: String): String = doctors.first { it.id == id }.name

    /** Allocated revenue of one doctor, excluding voided rows. */
    fun revenueOf(doctorId: String): Int = rows
        .filter { it.doctor == doctorId && !it.isVoid }
        .sumOf { it.revenue }

    /** Finance-owned invoices with money still to collect here. */
    val receivable: List<FinanceInvoice>
        get() = invoices.filter { it.due > 0 && it.source == "finance" }
}

/** One performer of a procedure entry. */
@Immutable
data class ProcedureShare(
    val doctor: String,
    /** Basis points of revenue; all shares of an entry sum to 10000. */
    val share: Int,
    /** Basis points of the fee rate. */
    val rate: Int,
)

/** A completed procedure to record; the server validates every field. */
@Immutable
data class ProcedureEntry(
    val patient: String,
    /** Existing invoice id, or empty to create a new invoice. */
    val invoice: String,
    val service: String,
    val date: String,
    val listPrice: Int,
    val discount: Int,
    val note: String,
    val people: List<ProcedureShare>,
)

/** Demo role headers sent with every request; not authentication. */
@Immutable
data class FinanceActor(val role: String, val doctor: String)

/** Value equality lets StateFlow skip polls that return the same projection. */
@Immutable
data class FinanceState(
    val month: String = financeMonth(),
    val role: String = "owner",
    val doctor: String = "D0",
    val error: String = "",
    /** Null until the first load and right after a role switch. */
    val data: FinanceSnapshot? = null,
    val sending: Boolean = false,
) {
    val actor: FinanceActor get() = FinanceActor(role = role, doctor = doctor)
    val private: Boolean get() = role == "doctor"
    val unread: Int get() = data?.unread ?: 0
}

/** Current month in Vietnam time (UTC+7), e.g. `2026-09`. */
@OptIn(ExperimentalTime::class)
fun financeMonth(nowMillis: Long? = null): String {
    val instant = nowMillis?.let(Instant::fromEpochMilliseconds) ?: Clock.System.now()
    val date = instant.toLocalDateTime(TimeZone.of("Asia/Ho_Chi_Minh")).date
    val month = date.month.ordinal + 1
    return "${date.year}-${month.toString().padStart(2, '0')}"
}
