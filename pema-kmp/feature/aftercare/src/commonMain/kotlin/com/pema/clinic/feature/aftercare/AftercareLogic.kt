package com.pema.clinic.feature.aftercare

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.listSaver
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

    /** A photo recovered after the screen was recreated (see `CameraService.recoveredPhotos`). */
    suspend fun attach(next: CapturedPhoto, camera: CameraService) {
        photo?.takeIf { it.path != next.path }?.let { camera.discard(it) }
        photo = next
    }

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

    fun submit(store: PatientsStore, patientId: String, camera: CameraService): Boolean {
        if (!canSend) return false
        store.submitPatientUpdate(patientId, text, photo?.path)
        photo?.let { camera.markSaved(it.path) }
        sent = true
        return true
    }

    suspend fun dispose(camera: CameraService) {
        val pending = photo
        if (!sent && pending != null) camera.discard(pending)
    }

    companion object {
        /** Keeps text, consent and the captured photo when Android recreates the screen. */
        val Saver: Saver<SendUpdateDraft, Any> = listSaver(
            save = { draft ->
                val p = draft.photo
                listOf(draft.text, draft.consent, p?.path ?: "", p?.width ?: 0, p?.height ?: 0, p?.bytes ?: 0L)
            },
            restore = { v ->
                val path = v[2] as String
                SendUpdateDraft(
                    initialText = v[0] as String,
                    initialConsent = v[1] as Boolean,
                    initialPhoto = if (path.isEmpty()) null else CapturedPhoto(path, v[3] as Int, v[4] as Int, v[5] as Long),
                )
            },
        )
    }
}
