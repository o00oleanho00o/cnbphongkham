package com.pema.clinic.feature.aftercare

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaEmpty
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicPatient
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.FollowUp
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.staffContext

fun NavGraphBuilder.followUpInboxGraph(deps: FeatureDeps) {
    composable(Routes.FollowUpInbox) { FollowUpInboxRoute(deps) }
}

internal enum class FollowUpInboxFilter(val label: String) {
    All("Tất cả"),
    Image("Ảnh"),
    Urgent("Triệu chứng"),
    Overdue("Quá hạn"),
}

@Immutable
internal data class FollowUpInboxUiState(
    val openCount: Int,
    val doctorCount: Int,
    val missedCount: Int,
    val imageCount: Int,
    val urgentCount: Int,
    val overdueCount: Int,
    val filter: FollowUpInboxFilter,
    val rows: List<FollowUpInboxRow>,
)

@Immutable
internal data class FollowUpInboxRow(
    val id: String,
    val patientId: String,
    val title: String,
    val sub: String,
    val icon: String,
)

internal fun followUpInboxState(
    state: ClinicState,
    staff: StaffContext = StaffContext(),
    filter: FollowUpInboxFilter = FollowUpInboxFilter.All,
): FollowUpInboxUiState {
    val open = state.followups
        .filter { it.status == "open" }
        .filter { staff.owns(state.patient(it.patient), state) }
    val visible = open.filter { followUp ->
        when (filter) {
            FollowUpInboxFilter.All -> true
            FollowUpInboxFilter.Image -> followUp.image != null
            FollowUpInboxFilter.Urgent -> followUp.priority == "urgent"
            FollowUpInboxFilter.Overdue -> followUp.priority == "overdue"
        }
    }
    return FollowUpInboxUiState(
        openCount = open.size,
        doctorCount = open.count { it.priority == "urgent" || it.priority == "review" },
        missedCount = open.count { it.priority == "missing" || it.priority == "overdue" },
        imageCount = open.count { it.image != null },
        urgentCount = open.count { it.priority == "urgent" },
        overdueCount = open.count { it.priority == "overdue" },
        filter = filter,
        rows = visible.map { it.toInboxRow(state.patient(it.patient)) },
    )
}

private fun FollowUp.toInboxRow(patient: ClinicPatient): FollowUpInboxRow = FollowUpInboxRow(
    id = id,
    patientId = patient.id,
    title = "$type · ${patient.name}",
    sub = buildString {
        append(symptom)
        append('\n')
        append(shortDayMonth(date))
        append(" · Giao: ")
        append(owner)
        if (image != null) append(" · có ảnh")
    },
    icon = when {
        image != null -> "photo_camera"
        priority == "urgent" -> "sick"
        priority == "missing" -> "no_photography"
        priority == "overdue" -> "schedule"
        else -> "schedule"
    },
)

@Composable
internal fun FollowUpInboxRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    var filter by rememberSaveable { mutableStateOf(FollowUpInboxFilter.All.name) }
    val selected = FollowUpInboxFilter.valueOf(filter)
    DetailScaffold(title = Routes.appBarTitleOf(Routes.FollowUpInbox)) {
        FollowUpInboxScreen(
            state = followUpInboxState(clinic, session.staffContext(), selected),
            onFilter = { filter = it.name },
            onOpen = { patientId ->
                val index = deps.catalogRepository.catalog().profiles.indexOfFirst { it.id == patientId }
                if (index >= 0) deps.sessionStore.select(index)
                deps.navigator.go(Routes.FollowUpReply)
            },
        )
    }
}

@Composable
internal fun FollowUpInboxScreen(
    state: FollowUpInboxUiState,
    onFilter: (FollowUpInboxFilter) -> Unit,
    onOpen: (String) -> Unit,
) {
    PemaHeading("Theo dõi", "Ảnh, triệu chứng và mốc bị bỏ sót")
    PemaMetrics(
        state.openCount.toString() to "Đang mở",
        state.doctorCount.toString() to "Cần bác sĩ",
        state.missedCount.toString() to "Bỏ sót",
    )
    Spacer(Modifier.height(16.dp))
    PemaChipWrap(Modifier.padding(bottom = 16.dp)) {
        PemaFilterChip("Tất cả ${state.openCount}", state.filter == FollowUpInboxFilter.All, { onFilter(FollowUpInboxFilter.All) })
        PemaFilterChip("Ảnh ${state.imageCount}", state.filter == FollowUpInboxFilter.Image, { onFilter(FollowUpInboxFilter.Image) })
        PemaFilterChip("Triệu chứng ${state.urgentCount}", state.filter == FollowUpInboxFilter.Urgent, { onFilter(FollowUpInboxFilter.Urgent) })
        PemaFilterChip("Quá hạn ${state.overdueCount}", state.filter == FollowUpInboxFilter.Overdue, { onFilter(FollowUpInboxFilter.Overdue) })
    }
    if (state.rows.isEmpty()) {
        PemaEmpty("Inbox đã sạch. Không có follow-up đang mở.", icon = "inbox")
    } else {
        state.rows.forEach { row ->
            PemaTile(
                title = row.title,
                sub = row.sub,
                icon = row.icon,
                onClick = { onOpen(row.patientId) },
            )
        }
    }
}

internal fun shortDayMonth(value: String): String {
    val date = value.take(10)
    val parts = date.split("-")
    if (parts.size != 3) return value
    return "${parts[2].toIntOrNull() ?: parts[2]}/${parts[1].toIntOrNull() ?: parts[1]}"
}
