package com.pema.clinic.feature.care

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.CrmInput
import com.pema.clinic.shared.clinic.crmOutcomes
import com.pema.clinic.shared.clinic.crmQueue
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.prepareCrmBooking
import com.pema.clinic.shared.clinic.resolveCrmTask
import com.pema.clinic.shared.clinic.staffContext

private val Channels = listOf("Gọi điện", "Zalo", "SMS")
private val NextActions = listOf("call", "review", "book", "message")
private val NextActionLabels = mapOf(
    "call" to "Gọi lại",
    "review" to "Bác sĩ xem",
    "book" to "Đặt lịch",
    "message" to "Nhắn chăm sóc",
)
private val Owners = listOf("CSKH Mai Anh", "CSKH Thu", "BS. Tâm", "BS. Mai", "BS. An", "BS. Lan")

fun NavGraphBuilder.careRecordGraph(deps: FeatureDeps) {
    composable(Routes.CareRecord) { CareRecordRoute(deps) }
}

@Composable
private fun CareRecordRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patientId = deps.sessionStore.selectedPatientId()
    val state = remember(clinic, patientId) { buildCareRecordState(clinic, patientId) }
    val messenger = rememberPemaMessenger()

    CareRecordScreen(
        state = state,
        onSave = { input ->
            val taskId = state.taskId ?: throw ClinicError("Không còn việc CSKH mở.")
            if (input.outcome == "booked") {
                deps.clinicStore.prepareCrmBooking(taskId, input, state.patientId, session.staffContext())
                deps.navigator.go(Routes.withArgs(Routes.AppointmentForm, "patient" to state.patientId, "crmTask" to taskId))
            } else {
                deps.clinicStore.resolveCrmTask(taskId, input, session.staffContext())
                messenger.show("Đã lưu kết quả và cập nhật hàng đợi")
            }
        },
    )
}

@Immutable
internal data class CareRecordUiState(
    val patientId: String,
    val patientName: String,
    val groupLabel: String,
    val remainingSessions: Int,
    val taskId: String?,
    val taskOwner: String,
    val defaultOutcome: String = "booked",
)

internal fun buildCareRecordState(state: ClinicState, patientId: String): CareRecordUiState {
    val patient = state.patient(patientId)
    val task = state.crmQueue(allDates = true, patient = patientId).firstOrNull()
    return CareRecordUiState(
        patientId = patient.id,
        patientName = patient.name,
        groupLabel = task?.reason?.replace(" D+", " · D+") ?: "Không còn việc CSKH mở",
        remainingSessions = maxOf(0, patient.total - patient.completed),
        taskId = task?.id,
        taskOwner = task?.owner ?: patient.crm.owner.ifBlank { "CSKH Thu" },
    )
}

@Composable
internal fun CareRecordScreen(
    state: CareRecordUiState,
    onSave: (CrmInput) -> Unit,
    modifier: Modifier = Modifier,
) {
    var channel by rememberSaveable(state.taskId) { mutableStateOf("Gọi điện") }
    var outcome by rememberSaveable(state.taskId) { mutableStateOf(state.defaultOutcome) }
    var note by rememberSaveable(state.taskId) { mutableStateOf("") }
    var nextAction by rememberSaveable(state.taskId) { mutableStateOf(if (outcome == "booked") "book" else "call") }
    var owner by rememberSaveable(state.taskId) { mutableStateOf(state.taskOwner.ifBlank { "CSKH Thu" }) }
    var nextActionAt by rememberSaveable(state.taskId) { mutableStateOf("") }
    var error by remember { mutableStateOf("") }

    DetailScaffold(title = Routes.appBarTitleOf(Routes.CareRecord), modifier = modifier) {
        PemaHeading(state.patientName, "${state.groupLabel} · Còn ${state.remainingSessions} buổi")
        PemaNotice("Ghi nhận cuộc gọi/tin nhắn mô phỏng. Không gửi Zalo/SMS hoặc thực hiện cuộc gọi thật.")
        if (state.taskId == null) {
            PemaEmpty("Không còn việc CSKH mở.")
            return@DetailScaffold
        }
        PemaChipWrap(Modifier.padding(bottom = 8.dp)) {
            Channels.forEach { option ->
                PemaFilterChip(option, selected = channel == option, onClick = { channel = option })
            }
        }
        Spacer(Modifier.height(8.dp))
        PemaDropdownField(
            value = outcome,
            options = crmOutcomes.keys.toList(),
            onSelected = {
                outcome = it
                if (it == "booked") nextAction = "book"
                error = ""
            },
            label = "Kết quả",
            display = { crmOutcomes.getValue(it) },
        )
        Spacer(Modifier.height(14.dp))
        PemaTextField(
            value = note,
            onValueChange = {
                note = it
                error = ""
            },
            label = "Nội dung / kết quả trao đổi",
            minLines = 2,
            maxLines = 2,
        )
        Spacer(Modifier.height(14.dp))
        PemaDropdownField(
            value = nextAction,
            options = NextActions,
            onSelected = { nextAction = it },
            label = "Hành động tiếp theo",
            display = { NextActionLabels.getValue(it) },
        )
        Spacer(Modifier.height(14.dp))
        PemaDropdownField(
            value = owner,
            options = (Owners + owner).distinct(),
            onSelected = { owner = it },
            label = "Phụ trách",
        )
        if (outcome in setOf("unanswered", "callback", "busy")) {
            Spacer(Modifier.height(14.dp))
            PemaTextField(
                value = nextActionAt,
                onValueChange = {
                    nextActionAt = it
                    error = ""
                },
                label = "Ngày giờ tiếp theo",
                hint = "2026-09-21T09:00",
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            )
        }
        Spacer(Modifier.height(8.dp))
        if (error.isNotEmpty()) {
            Text(error, style = PemaType.of(14f, color = PemaColors.Error))
            Spacer(Modifier.height(8.dp))
        }
        PemaPrimary(
            "Lưu kết quả chăm sóc",
            onClick = {
                val input = CrmInput(
                    channel = channel,
                    outcome = outcome,
                    note = note,
                    nextActionType = nextAction,
                    nextActionAt = nextActionAt.ifBlank { null },
                    owner = owner,
                )
                try {
                    onSave(input)
                    error = ""
                } catch (e: ClinicError) {
                    error = e.message.orEmpty()
                }
            },
        )
        PemaText("Đồng ý đặt lịch sẽ mở form lịch trước khi hoàn tất.", size = 12f, color = PemaColors.Muted)
    }
}
