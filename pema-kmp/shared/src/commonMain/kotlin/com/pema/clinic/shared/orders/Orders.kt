package com.pema.clinic.shared.orders

import androidx.compose.runtime.Immutable
import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.patients.CartLine
import com.pema.clinic.shared.patients.PatientsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

@Immutable
data class Order(
    val id: String,
    val patientId: String,
    val patientName: String,
    val approved: Boolean,
    val items: List<CartLine>,
) {
    val total: Int get() = items.sumOf { it.total }
}

class OrdersStore(private val patients: PatientsStore, private val catalog: CatalogRepository) {
    private val mutableState = MutableStateFlow<List<Order>>(emptyList())
    val state: StateFlow<List<Order>> = mutableState.asStateFlow()

    /** Moves the patient's cart into a draft or approved order and clears it. */
    fun save(patientId: String, approve: Boolean) {
        val patient = patients.of(patientId)
        if (patient.cart.isEmpty() || (approve && !patient.cartReady)) {
            error("Cần phân loại và nhập hướng dẫn trước khi duyệt")
        }
        val existing = mutableState.value.indexOfFirst { it.id == patient.editingOrder }
        val order = Order(
            id = patient.editingOrder ?: "DN-${mutableState.value.size + 1}",
            patientId = patientId,
            patientName = catalog.profile(patientId).name,
            approved = approve,
            items = patient.cart,
        )
        mutableState.value = if (existing < 0) {
            mutableState.value + order
        } else {
            mutableState.value.mapIndexed { index, current -> if (index == existing) order else current }
        }
        patients.update(patientId) { it.copy(cart = emptyList(), editingOrder = null) }
    }

    fun edit(patientId: String, order: Order) = patients.update(patientId) {
        it.copy(cart = order.items, editingOrder = order.id)
    }

    fun patientOrders(id: String): List<Order> = state.value.filter { it.patientId == id }
}
