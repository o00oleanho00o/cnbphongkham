package com.pema.clinic.shared.care

import com.pema.clinic.shared.catalog.CatalogRepository
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientsStore
import com.pema.clinic.shared.session.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/** Owned profiles that need a doctor's review: D+7, a patient update or CSKH escalation. */
class ReviewQueue(
    private val catalog: CatalogRepository,
    private val patients: PatientsStore,
    private val session: SessionStore,
    scope: CoroutineScope,
) {
    private val mutableState = MutableStateFlow(buildProfiles())
    val state: StateFlow<List<PatientProfile>> = mutableState.asStateFlow()

    init {
        scope.launch {
            combine(patients.state, session.state) { _, _ -> buildProfiles() }
                .collect { mutableState.value = it }
        }
    }

    fun profiles(): List<PatientProfile> = state.value

    private fun buildProfiles(): List<PatientProfile> = catalog.catalog().profiles.filter { profile ->
        session.state.value.owns(profile) &&
            (profile.hasTask("d7") ||
                patients.of(profile.id).updates.isNotEmpty() ||
                patients.of(profile.id).escalations.isNotEmpty())
    }
}
