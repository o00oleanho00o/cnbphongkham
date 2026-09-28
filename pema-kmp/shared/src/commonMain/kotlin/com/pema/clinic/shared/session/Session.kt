package com.pema.clinic.shared.session

import com.pema.clinic.core.common.Routes
import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.catalog.PatientProfile
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

private val careRoutes = setOf(
    Routes.MyAppointments,
    Routes.HomeCare,
    Routes.SendUpdate,
    Routes.TreatmentPlan,
    Routes.ProgressPhotos,
    Routes.Prescriptions,
    Routes.Invoices,
    Routes.Privacy,
    Routes.Guide,
)
private val customerCareRoutes = setOf(
    Routes.CustomerCare,
    Routes.Booking,
    Routes.AppointmentDetail,
    Routes.Guide,
)
private val accountantRoutes = setOf(
    Routes.Cashier,
    Routes.Invoices,
    Routes.Guide,
)
private val doctorBlockedRoutes = setOf(
    Routes.Cashier,
    Routes.Resources,
    Routes.Services,
    Routes.CustomerCare,
)

/** Demo workspace switch; not authentication or RBAC. */
data class Session(
    val careMode: Boolean = false,
    val staffRole: String = "owner",
    val staffDoctor: String = "BS. Tâm",
    val staffName: String = "BS. Tâm",
    val staffSelected: Int = 0,
    val careSelected: Int = 0,
) {
    val selected: Int get() = if (careMode) careSelected else staffSelected
    val billing: Boolean get() = !careMode && (staffRole == "owner" || staffRole == "accountant")
    val clinical: Boolean get() = !careMode && (staffRole == "owner" || staffRole == "doctor")

    fun owns(profile: PatientProfile): Boolean = staffRole != "doctor" || profile.doctor == staffDoctor

    fun allows(route: String): Boolean {
        val routeId = Routes.idOf(route) ?: route
        if (careMode) return careRoutes.contains(routeId)
        return when (staffRole) {
            "owner" -> true
            "care" -> customerCareRoutes.contains(routeId)
            "accountant" -> accountantRoutes.contains(routeId)
            else -> !doctorBlockedRoutes.contains(routeId)
        }
    }
}

class SessionStore(private val catalog: CatalogRepository) {
    private val mutableState = MutableStateFlow(Session())
    val state: StateFlow<Session> = mutableState.asStateFlow()

    fun select(index: Int) {
        mutableState.value = mutableState.value.let { current ->
            if (current.careMode) current.copy(careSelected = index) else current.copy(staffSelected = index)
        }
    }

    fun enterCare() {
        mutableState.value = mutableState.value.copy(careMode = true)
    }

    fun enterStaff(role: String, name: String) {
        var next = mutableState.value.copy(
            careMode = false,
            staffRole = role,
            staffName = name,
            staffDoctor = name,
        )
        val profiles = catalog.catalog().profiles
        if (!next.owns(profiles[next.staffSelected])) {
            next = next.copy(staffSelected = profiles.indexOfFirst { it.doctor == next.staffDoctor })
        }
        mutableState.value = next
    }

    fun selectedProfile(): PatientProfile = catalog.catalog().profiles[state.value.selected]

    fun selectedPatientId(): String = selectedProfile().id
}
