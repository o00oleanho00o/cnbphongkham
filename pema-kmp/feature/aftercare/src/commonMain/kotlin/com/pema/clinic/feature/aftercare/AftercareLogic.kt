package com.pema.clinic.feature.aftercare

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.pema.clinic.core.hardware.CameraService
import com.pema.clinic.core.hardware.CapturedPhoto
import com.pema.clinic.core.hardware.HardwareFailure
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.patients.PatientsStore

internal fun canSendUpdate(text: String, hasPhoto: Boolean, consent: Boolean): Boolean =
    text.trim().isNotEmpty() && (!hasPhoto || consent)

internal fun canSendReply(text: String): Boolean = text.trim().isNotEmpty()

internal fun PatientState.withAcknowledgedInstructions(): PatientState = copy(acknowledged = true)

internal fun PatientState.withPatientUpdate(text: String, photoPath: String?): PatientState =
    copy(
        updates = updates + text,
        photos = if (photoPath == null) photos else photos + photoPath,
    )

internal fun PatientState.withDoctorReply(text: String): PatientState = copy(response = text)

internal fun PatientsStore.acknowledgeInstructions(id: String) =
    update(id) { it.withAcknowledgedInstructions() }

internal fun PatientsStore.submitPatientUpdate(id: String, text: String, photoPath: String?) =
    update(id) { it.withPatientUpdate(text, photoPath) }

internal fun PatientsStore.submitDoctorReply(id: String, text: String) =
    update(id) { it.withDoctorReply(text) }

internal class SendUpdateDraft(
    initialText: String = "",
    initialConsent: Boolean = false,
    initialPhoto: CapturedPhoto? = null,
) {
    var text by mutableStateOf(initialText)
    var consent by mutableStateOf(initialConsent)
    var capturing by mutableStateOf(false)
        private set
    var sent by mutableStateOf(false)
        private set
    var photo by mutableStateOf(initialPhoto)
        private set

    val canSend: Boolean get() = canSendUpdate(text, photo != null, consent)

    suspend fun capture(camera: CameraService): String? {
        capturing = true
        return try {
            val next = camera.capture()
            if (next != null) {
                photo?.let { camera.discard(it) }
                photo = next
            }
            null
        } catch (failure: HardwareFailure) {
            failure.message ?: "Không thể chụp ảnh."
        } finally {
            capturing = false
        }
    }

    suspend fun removePhoto(camera: CameraService) {
        photo?.let { camera.discard(it) }
        photo = null
        consent = false
    }

    fun submit(store: PatientsStore, patientId: String): Boolean {
        if (!canSend) return false
        store.submitPatientUpdate(patientId, text, photo?.path)
        sent = true
        return true
    }

    suspend fun dispose(camera: CameraService) {
        val pending = photo
        if (!sent && pending != null) camera.discard(pending)
    }
}
