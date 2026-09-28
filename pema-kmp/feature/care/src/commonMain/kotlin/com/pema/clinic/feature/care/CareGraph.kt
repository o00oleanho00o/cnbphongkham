package com.pema.clinic.feature.care

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientState

fun NavGraphBuilder.careGraph(deps: FeatureDeps) {
    composable(Routes.CustomerCare) { CustomerCareContactScreen(deps) }
}

@Composable
internal fun CustomerCareContactScreen(deps: FeatureDeps) {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patients by deps.patientsStore.state.collectAsStateWithLifecycle()
    val catalog = deps.catalogRepository.catalog()
    val profile = catalog.profiles[session.selected.coerceIn(catalog.profiles.indices)]
    val patient = patients[profile.id] ?: PatientState.fromProfile(profile)
    val messenger = rememberPemaMessenger()
    var text by rememberSaveable(profile.id) { mutableStateOf("") }

    fun toast(message: String) {
        messenger.show(message)
    }

    fun saveContact() {
        val note = text.trim()
        if (note.isEmpty()) {
            toast("Nhập kết quả liên hệ")
            return
        }
        deps.patientsStore.update(profile.id) { it.copy(careNote = note, careStatus = "Đã liên hệ") }
        toast("Đã lưu ghi chú nội bộ")
    }

    fun handOffToDoctor() {
        val note = text.trim()
        if (note.isEmpty()) {
            toast("Nhập nội dung cần bác sĩ xem")
            return
        }
        deps.patientsStore.update(profile.id) {
            it.copy(careNote = note, careStatus = "Chờ bác sĩ", escalations = it.escalations + note)
        }
        toast("Đã chuyển vào hàng chờ bác sĩ")
    }

    CustomerCareContactContent(
        profile = profile,
        patient = patient,
        text = text,
        onTextChange = { text = it },
        onSave = ::saveContact,
        onRebook = { deps.navigator.go(Routes.Booking) },
        onHandOff = ::handOffToDoctor,
        onFullRecord = { deps.navigator.go(Routes.CareRecord) },
    )
}

@Composable
internal fun CustomerCareContactContent(
    profile: PatientProfile,
    patient: PatientState,
    text: String,
    onTextChange: (String) -> Unit,
    onSave: () -> Unit,
    onRebook: () -> Unit,
    onHandOff: () -> Unit,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = LocalOnBack.current,
    /** Web CRM "Xử lý" form (canvas I13); null hides the link (Flutter C6 has none). */
    onFullRecord: (() -> Unit)? = null,
) {
    DetailScaffold(title = Routes.titleOf(Routes.CustomerCare), modifier = modifier, onBack = onBack) {
        PemaHeading(profile.name, "${profile.id} · ${profile.caseLabel}")
        PemaNotice("Nội dung liên hệ nội bộ không hiển thị cho người bệnh.")
        if (patient.careNote.isNotEmpty()) {
            PemaNotice(patient.careNote)
        }
        PemaTextField(
            value = text,
            onValueChange = onTextChange,
            label = "Kết quả liên hệ / việc cần bàn giao",
            minLines = 3,
            maxLines = 3,
        )
        PemaPrimary("Lưu kết quả liên hệ", onClick = onSave)
        Spacer(Modifier.height(12.dp))
        PemaOutlinedButton("Hỗ trợ đặt lại lịch", onClick = onRebook, icon = "calendar_month")
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PemaTextButton("Chuyển bác sĩ xem", onClick = onHandOff, icon = "forward_to_inbox")
        }
        if (onFullRecord != null) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PemaTextButton("Ghi nhận CSKH đầy đủ", onClick = onFullRecord, icon = "fact_check")
            }
        }
    }
}
