package com.pema.clinic.shared.patients

import androidx.compose.runtime.Immutable
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.catalog.Product
import com.pema.clinic.shared.care.careNotContacted

@Immutable
data class CartLine(
    val product: Product,
    /** Output route chosen by the doctor; starts as the catalog's `outputType`. */
    val route: String = product.outputType,
    val quantity: Int = 1,
    val usage: String = "",
) {
    val code: String get() = product.code
    val name: String get() = product.name
    val unit: String get() = product.unit
    val total: Int get() = product.price * quantity

    companion object {
        fun of(product: Product): CartLine = CartLine(product = product, route = product.outputType)
    }
}

/** Session-only clinical, schedule, care and cart state for one patient. */
@Immutable
data class PatientState(
    val sessions: Int,
    val appointment: String,
    val day: String,
    val checkedIn: Boolean = false,
    val confirmed: Boolean = false,
    val acknowledged: Boolean = false,
    val note: String = "",
    val response: String = "",
    val careNote: String = "",
    val careStatus: String = careNotContacted,
    val editingOrder: String? = null,
    val cart: List<CartLine> = emptyList(),
    val updates: List<String> = emptyList(),
    /** Local paths of progress photos the patient sent, oldest first. */
    val photos: List<String> = emptyList(),
    /** Internal CSKH hand-offs; never shown in Care. */
    val escalations: List<String> = emptyList(),
) {
    val cartTotal: Int get() = cart.sumOf { it.total }
    val cartReady: Boolean
        get() = cart.isNotEmpty() && cart.all { it.route != "UNRESOLVED" && it.usage.trim().isNotEmpty() }

    companion object {
        fun fromProfile(profile: PatientProfile): PatientState = PatientState(
            sessions = profile.sessions,
            appointment = profile.appointment,
            day = profile.day,
        )
    }
}
