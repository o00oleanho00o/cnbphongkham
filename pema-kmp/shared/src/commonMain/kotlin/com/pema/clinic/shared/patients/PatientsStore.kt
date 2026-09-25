package com.pema.clinic.shared.patients

import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.catalog.Product
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class PatientsStore(private val catalog: CatalogRepository) {
    private val mutableState = MutableStateFlow<Map<String, PatientState>>(emptyMap())
    val state: StateFlow<Map<String, PatientState>> = mutableState.asStateFlow()

    fun of(id: String): PatientState = mutableState.value[id] ?: PatientState.fromProfile(catalog.profile(id))

    fun update(id: String, change: (PatientState) -> PatientState) {
        mutableState.value = mutableState.value + (id to change(of(id)))
    }

    fun addToCart(id: String, product: Product) = update(id) { patient ->
        val index = patient.cart.indexOfFirst { it.code == product.code }
        if (index < 0) {
            patient.copy(cart = patient.cart + CartLine.of(product))
        } else {
            patient.copy(
                cart = patient.cart.mapIndexed { i, line ->
                    if (i == index) line.copy(quantity = line.quantity + 1) else line
                },
            )
        }
    }

    fun updateLine(id: String, index: Int, change: (CartLine) -> CartLine) = update(id) { patient ->
        patient.copy(
            cart = patient.cart.mapIndexed { i, line -> if (i == index) change(line) else line },
        )
    }

    fun removeLine(id: String, index: Int) = update(id) { patient ->
        patient.copy(cart = patient.cart.toMutableList().also { it.removeAt(index) })
    }

    fun addPhoto(id: String, path: String) = update(id) { it.copy(photos = it.photos + path) }
    fun removePhoto(id: String, path: String) = update(id) { patient ->
        patient.copy(photos = patient.photos.filterNot { it == path })
    }
    fun addUpdate(id: String, text: String) = update(id) { it.copy(updates = it.updates + text) }
    fun escalate(id: String, reason: String) = update(id) { it.copy(escalations = it.escalations + reason) }
}
