package com.pema.clinic.feature.patients

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.core.ui.widgets.LocalPhoto
import com.pema.clinic.core.ui.widgets.PemaCheckRow
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaMetrics
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.Catalog
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.finance.FinanceState
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session

fun NavGraphBuilder.patientsGraph(deps: FeatureDeps) {
    composable(Routes.Patient360) { Patient360Route(deps) }
    composable(Routes.Consultation) { ConsultationRoute(deps) }
    composable(Routes.TreatmentPlan) { TreatmentPlanRoute(deps) }
    composable(Routes.TreatmentSession) { TreatmentSessionRoute(deps) }
    composable(Routes.ProgressPhotos) { ProgressPhotosRoute(deps) }
    composable(Routes.AskPema) { AskPemaRoute(deps) }
}

internal data class SelectedPatient(
    val catalog: Catalog,
    val session: Session,
    val profile: PatientProfile,
    val patient: PatientState,
)

internal data class ProgressPhotoSlots(val before: String?, val latest: String?)

@Composable
internal fun selectedPatient(deps: FeatureDeps): SelectedPatient {
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patients by deps.patientsStore.state.collectAsStateWithLifecycle()
    val catalog = deps.catalogRepository.catalog()
    val index = session.selected.coerceIn(0, catalog.profiles.lastIndex)
    val profile = catalog.profiles[index]
    val patient = patients[profile.id] ?: PatientState.fromProfile(profile)
    return SelectedPatient(catalog = catalog, session = session, profile = profile, patient = patient)
}

internal fun shouldShowProcedureRecordCard(session: Session, finance: FinanceState): Boolean =
    !session.careMode && session.billing && finance.data != null && finance.role != "doctor"

internal fun canCompleteTreatmentSession(
    patient: PatientState,
    totalSessions: Int,
    record: String,
    handoverChecked: Boolean,
): Boolean = handoverChecked && record.trim().isNotEmpty() && patient.sessions < totalSessions

internal fun progressPhotoSlots(photos: List<String>): ProgressPhotoSlots = ProgressPhotoSlots(
    before = if (photos.size > 1) photos.first() else null,
    latest = photos.lastOrNull(),
)

@Composable
internal fun Patient360Route(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    val finance by deps.financeStore.state.collectAsStateWithLifecycle()
    DetailScaffold(title = Routes.titleOf(Routes.Patient360)) {
        PemaHeading(selected.profile.name, "${selected.profile.id} · ${selected.profile.doctor}")
        PemaNotice("Da nhạy cảm • Cần đọc tiền sử trước khi kê đơn")
        PemaMetrics(
            "${selected.patient.sessions}/${selected.profile.totalSessions}" to "Buổi điều trị",
            selected.patient.appointment to "Lịch tiếp theo",
        )
        if (shouldShowProcedureRecordCard(selected.session, finance)) {
            PemaTile(
                title = "Ghi nhận tiền thủ thuật",
                sub = "Đúng người thực hiện · gắn hóa đơn đã có",
                icon = "receipt_long",
                onClick = { deps.navigator.go(Routes.FinanceProcedure) },
            )
        }
        PemaSection("Hồ sơ xuyên suốt")
        listOf(
            Routes.Consultation,
            Routes.TreatmentPlan,
            Routes.TreatmentSession,
            Routes.ProgressPhotos,
            Routes.QuickOrder,
            Routes.Prescriptions,
            Routes.Invoices,
        ).forEach { route ->
            PemaTile(
                title = Routes.titleOf(route),
                sub = "Xem và cập nhật",
                icon = "chevron_right",
                onClick = { deps.navigator.go(route) },
            )
        }
        PemaPrimary(
            text = if (selected.patient.checkedIn) "Đã check-in" else "Check-in người bệnh",
            onClick = if (selected.patient.checkedIn) {
                null
            } else {
                { deps.patientsStore.update(selected.profile.id) { it.copy(checkedIn = true) } }
            },
        )
    }
}

@Composable
internal fun ConsultationRoute(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    val messenger = rememberPemaMessenger()
    var note by remember(selected.profile.id) { mutableStateOf("") }
    DetailScaffold(title = Routes.titleOf(Routes.Consultation)) {
        PemaNotice("Ghi chú chuyên môn là bản nháp, cần bác sĩ xem lại.")
        PemaTextField(
            value = note,
            onValueChange = { note = it },
            label = "Ghi chú tư vấn",
            hint = selected.patient.note,
            minLines = 6,
            maxLines = 6,
        )
        PemaPrimary(
            text = "Lưu ghi chú nháp",
            onClick = {
                deps.patientsStore.update(selected.profile.id) { it.copy(note = note) }
                messenger.show("Đã lưu ghi chú")
            },
        )
        PemaPrimary("Xem tóm tắt AI", onClick = { deps.navigator.go(Routes.AskPema) })
    }
}

@Composable
internal fun TreatmentSessionRoute(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    val messenger = rememberPemaMessenger()
    var record by remember(selected.profile.id) { mutableStateOf("") }
    var handoverChecked by remember(selected.profile.id) { mutableStateOf(false) }
    val enabled = canCompleteTreatmentSession(
        patient = selected.patient,
        totalSessions = selected.profile.totalSessions,
        record = record,
        handoverChecked = handoverChecked,
    )
    DetailScaffold(title = Routes.titleOf(Routes.TreatmentSession)) {
        PemaNotice("Buổi ${selected.patient.sessions + 1}/${selected.profile.totalSessions} · ${selected.profile.doctor}")
        PemaTextField(
            value = record,
            onValueChange = { record = it },
            label = "Ghi nhận buổi điều trị *",
            minLines = 4,
            maxLines = 4,
        )
        PemaCheckRow(
            label = "Đã kiểm tra và bàn giao aftercare",
            checked = handoverChecked,
            onCheckedChange = { handoverChecked = it },
        )
        PemaPrimary(
            text = "Hoàn tất buổi",
            onClick = if (enabled) {
                {
                    deps.patientsStore.update(selected.profile.id) { it.copy(sessions = it.sessions + 1) }
                    messenger.show("Đã lưu buổi và cập nhật hành trình")
                    deps.navigator.back()
                }
            } else {
                null
            },
        )
    }
}

@Composable
internal fun AskPemaRoute(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    DetailScaffold(title = Routes.titleOf(Routes.AskPema)) {
        PemaHero(
            title = "Bối cảnh trước\nmỗi quyết định.",
            sub = "AI mô phỏng • cần bác sĩ kiểm tra",
            icon = "auto_awesome",
        )
        PemaSection("Tóm tắt ${selected.profile.name}")
        PemaNotice(
            "Đã hoàn tất ${selected.patient.sessions}/${selected.profile.totalSessions} buổi. " +
                "Có ${selected.patient.updates.size} phản hồi tại nhà.\n" +
                "Nguồn: hành trình và cập nhật trong phiên mẫu.",
        )
        PemaTile(
            title = "Việc còn mở",
            sub = "Xem phản hồi trước khi khám lại.",
            icon = "inbox",
            onClick = { deps.navigator.go(Routes.FollowUpReply) },
        )
        PemaPrimary("Mở ghi chú để bác sĩ sửa", onClick = { deps.navigator.go(Routes.Consultation) })
    }
}

@Composable
internal fun TreatmentPlanRoute(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    DetailScaffold(title = Routes.titleOf(Routes.TreatmentPlan)) {
        PemaHero(
            title = "Phục hồi & chăm sóc da",
            sub = "${selected.patient.sessions}/${selected.profile.totalSessions} buổi · BS. Tâm",
            icon = "route",
        )
        PemaSection("Các mốc chăm sóc")
        for (i in 1..5) {
            val done = i <= selected.patient.sessions
            PemaTile(
                title = "Buổi $i",
                sub = if (done) "Đã hoàn tất" else "Chờ đánh giá / thực hiện",
                icon = if (done) "check_circle" else "circle",
                onClick = null,
            )
        }
        PemaPrimary("Xem chăm sóc tại nhà", onClick = { deps.navigator.go(Routes.HomeCare) })
    }
}

@Composable
internal fun ProgressPhotosRoute(deps: FeatureDeps) {
    val selected = selectedPatient(deps)
    val photos = selected.patient.photos
    val slots = progressPhotoSlots(photos)
    DetailScaffold(title = Routes.titleOf(Routes.ProgressPhotos)) {
        PemaHeading(
            title = "Theo dõi bằng hình ảnh",
            sub = if (photos.isEmpty()) {
                "Ảnh minh họa • không đánh giá hiệu quả tự động"
            } else {
                "${photos.size} ảnh đã gửi • không đánh giá hiệu quả tự động"
            },
        )
        Row(Modifier.fillMaxWidth()) {
            ProgressPhotoSlot("Trước", slots.before)
            ProgressPhotoSlot("Gần nhất", slots.latest)
        }
        PemaNotice("Chính diện · Vùng mặt · Cần cùng điều kiện ánh sáng")
        PemaPrimary("Gửi ảnh cập nhật", onClick = { deps.navigator.go(Routes.SendUpdate) })
    }
}

@Composable
private fun RowScope.ProgressPhotoSlot(label: String, path: String?) {
    Box(Modifier.weight(1f).padding(4.dp)) {
        if (path != null) {
            LocalPhoto(path = path, label = label)
        } else {
            IllustratedPhotoTile(label)
        }
    }
}

@Composable
private fun IllustratedPhotoTile(label: String) {
    Column(
        Modifier
            .fillMaxWidth()
            .height(220.dp)
            .background(PemaColors.Tint, RoundedCornerShape(18.dp)),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        PemaIcon("face", size = 76.dp, color = PemaColors.PhotoIcon)
        Text(label, style = PemaType.body)
        Text("Minh họa", style = PemaType.of(11f, color = PemaColors.Ink))
    }
}
