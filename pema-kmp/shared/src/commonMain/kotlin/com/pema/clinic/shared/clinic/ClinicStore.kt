package com.pema.clinic.shared.clinic

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Atomic in-memory store for clinic prototype state. */
class ClinicStore(initial: ClinicState = ClinicSeed.initial()) {
    private val mutableState = MutableStateFlow(initial)

    /** Current immutable state as a flow for UI agents. */
    val state: StateFlow<ClinicState> = mutableState.asStateFlow()

    /** Returns a patient by id, or the selected/default patient when [id] is omitted. */
    fun patient(id: String? = null): ClinicPatient =
        mutableState.value.patient(id ?: mutableState.value.selected)

    /**
     * Applies [block] atomically. If [block] throws (including [ClinicError]), the state is
     * unchanged and the exception propagates.
     */
    fun <T> transact(block: (ClinicState) -> Pair<ClinicState, T>): T {
        val before = mutableState.value
        val (after, result) = block(before)
        mutableState.value = after
        return result
    }
}

/** Looks up a patient or throws a domain error. */
fun ClinicState.patient(id: String): ClinicPatient =
    patients.find { it.id == id } ?: throw ClinicError("Không tìm thấy hồ sơ bệnh nhân.")

internal fun ClinicState.updatePatient(id: String, transform: (ClinicPatient) -> ClinicPatient): ClinicState =
    copy(patients = patients.map { if (it.id == id) transform(it) else it })

/** Prepends an audit row with the fixed demo actor. */
fun ClinicState.log(action: String, patient: String): ClinicState =
    copy(audit = listOf(AuditEntry(action, patient, "${DAY}T09:00:00+07:00")) + audit)

/** Prepends a patient timeline event with deterministic ids. */
fun ClinicState.addEvent(
    patientId: String,
    kind: String,
    title: String,
    detail: String,
    by: String = "BS. Tâm",
    date: String = DAY,
): ClinicState = updatePatient(patientId) { patient ->
    val id = "e-${audit.size + crmActivities.size + patient.events.size + 1}"
    patient.copy(events = listOf(PatientEvent(id, kind, date, title, detail, by)) + patient.events)
}
