package com.pema.clinic.shared.billing

import androidx.compose.runtime.Immutable
import com.pema.clinic.shared.orders.OrdersStore
import com.pema.clinic.shared.session.SessionStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** What one patient owes across their orders and what has been collected. */
@Immutable
data class Bill(val total: Int, val paid: Int) {
    val due: Int get() = total - paid
    val settled: Boolean get() = due <= 0
}

/** Demo cash totals per patient; no ledger or bank connection. */
class ReceiptsStore(private val session: SessionStore, private val orders: OrdersStore) {
    private val mutableState = MutableStateFlow<Map<String, Int>>(emptyMap())
    val state: StateFlow<Map<String, Int>> = mutableState.asStateFlow()

    fun settle(patientId: String, total: Int) {
        mutableState.value = mutableState.value + (patientId to total)
    }

    fun paidFor(patientId: String): Int = state.value[patientId] ?: 0

    fun billFor(patientId: String): Bill = Bill(
        total = orders.patientOrders(patientId).sumOf { it.total },
        paid = paidFor(patientId),
    )

    fun currentPaid(): Int = paidFor(session.selectedPatientId())

    fun currentBill(): Bill = billFor(session.selectedPatientId())
}
