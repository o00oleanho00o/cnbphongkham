package com.pema.clinic.feature.patients

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.hardware.CapturedPhoto
import com.pema.clinic.core.hardware.HardwareFailure
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.theme.PemaType
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalPhoto
import com.pema.clinic.core.ui.widgets.OnScreenCleared
import com.pema.clinic.core.ui.widgets.PemaPhotoSourceSheet
import com.pema.clinic.core.ui.widgets.PemaCardLine
import com.pema.clinic.core.ui.widgets.PemaCardTitle
import com.pema.clinic.core.ui.widgets.PemaCheckRow
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaDropdownField
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaInfoCard
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicPatient
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.PlanEditInput
import com.pema.clinic.shared.clinic.StaffContext
import com.pema.clinic.shared.clinic.TreatmentSessionInput
import com.pema.clinic.shared.clinic.addDays
import com.pema.clinic.shared.clinic.approveAiBrief
import com.pema.clinic.shared.clinic.approveConsultDraft
import com.pema.clinic.shared.clinic.brief
import com.pema.clinic.shared.clinic.generateConsultDraft
import com.pema.clinic.shared.clinic.patient
import com.pema.clinic.shared.clinic.recordTreatmentSession
import com.pema.clinic.shared.clinic.saveClinicalNote
import com.pema.clinic.shared.clinic.staffContext
import com.pema.clinic.shared.clinic.updateTreatmentPlan
import com.pema.clinic.shared.clinic.viDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

fun NavGraphBuilder.patient360ClinicalGraph(deps: FeatureDeps) {
    composable(Routes.ClinicalHistory) { ClinicalHistoryRoute(deps) }
    composable(Routes.AiBrief) { AiBriefRoute(deps) }
    composable(Routes.PlanOverview) { PlanOverviewRoute(deps) }
    composable(Routes.PlanEdit) { PlanEditRoute(deps) }
    composable(Routes.SessionRecord) { SessionRecordRoute(deps) }
}

@Immutable
internal data class ClinicalHistoryUiState(
    val patientName: String,
    val history: String,
    val diagnosis: String,
    val transcript: String,
    val draft: String,
    val canClinical: Boolean = true,
)

@Immutable
internal data class AiBriefUiState(
    val patientName: String,
    val plan: String,
    val text: String,
    val canClinical: Boolean = true,
)

@Immutable
internal data class PlanOverviewUiState(
    val plan: String,
    val completed: Int,
    val total: Int,
    val doctor: String,
    val goal: String,
    val milestones: List<PlanMilestone>,
    val photoCriterion: String,
    val reportedOutcome: String,
    val reminder: String,
    val canClinical: Boolean = true,
)

@Immutable
internal data class PlanMilestone(val title: String, val sub: String, val icon: String)

@Immutable
internal data class PlanEditUiState(val name: String, val total: String, val completed: Int, val canClinical: Boolean = true)

@Immutable
internal data class SessionRecordUiState(
    val notice: String,
    val sessionType: String,
    val protocol: String,
    val nextVisit: String,
    val region: String,
    val view: String,
    val consent: Boolean,
    val photoSelected: Boolean = false,
    /** Local landmark photo (camera or picker), shown as a preview. */
    val photoPath: String? = null,
    val photoBusy: Boolean = false,
    val canClinical: Boolean = true,
)

internal val sessionTypes = listOf("Chăm sóc & laser theo chỉ định", "Tái khám đánh giá", "Chăm sóc phục hồi")
internal val protocolOptions = listOf("Theo khuyến nghị bác sĩ", "Laser CO2 · D+1 / D+3 / D+7 / D+30")
internal val regions = listOf("Mặt", "Cổ", "Vùng khác")
internal val views = listOf("Chính diện", "Má trái", "Má phải")

@Composable
internal fun ClinicalHistoryRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val staff = session.staffContext()
    val patient = clinic.patient(deps.sessionStore.selectedPatientId())
    var history by rememberSaveable(patient.id) { mutableStateOf(patient.clinical?.history.orEmpty()) }
    var diagnosis by rememberSaveable(patient.id) { mutableStateOf(patient.clinical?.diagnosis.orEmpty()) }
    var transcript by rememberSaveable(patient.id) { mutableStateOf("") }
    var draft by rememberSaveable(patient.id) { mutableStateOf(patient.notes) }
    val messenger = rememberPemaMessenger()
    ClinicalHistoryScreen(
        state = ClinicalHistoryUiState(patient.name, history, diagnosis, transcript, draft, canClinical = staff.can("clinical")),
        onHistoryChange = { history = it },
        onDiagnosisChange = { diagnosis = it },
        onTranscriptChange = { transcript = it },
        onDraftChange = { draft = it },
        onSaveClinical = {
            runClinicAction(messenger) {
                deps.clinicStore.saveClinicalNote(patient.id, history, diagnosis, staff)
                messenger.show("Đã lưu nhận định có bác sĩ xác nhận")
            }
        },
        onGenerateDraft = {
            runClinicAction(messenger) {
                draft = deps.clinicStore.generateConsultDraft(patient.id, transcript, staff).draft
                messenger.show("Đã tạo bản nháp — hãy kiểm tra trước khi duyệt")
            }
        },
        onApproveDraft = {
            runClinicAction(messenger) {
                deps.clinicStore.approveConsultDraft(patient.id, draft, staff)
                draft = ""
                messenger.show("Đã duyệt và nối vào Patient 360")
            }
        },
    )
}

@Composable
internal fun ClinicalHistoryScreen(
    state: ClinicalHistoryUiState,
    onHistoryChange: (String) -> Unit,
    onDiagnosisChange: (String) -> Unit,
    onTranscriptChange: (String) -> Unit,
    onDraftChange: (String) -> Unit,
    onSaveClinical: () -> Unit,
    onGenerateDraft: () -> Unit,
    onApproveDraft: () -> Unit,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.ClinicalHistory)) {
        PemaHeading(state.patientName, "Bác sĩ ghi nhận · không dùng AI tự chẩn đoán")
        PemaTextField(state.history, onHistoryChange, label = "Tiền sử đã khai thác", minLines = 2, maxLines = 2)
        Spacer(Modifier.height(14.dp))
        PemaTextField(state.diagnosis, onDiagnosisChange, label = "Khám / chẩn đoán do bác sĩ xác nhận", minLines = 2, maxLines = 2)
        if (state.canClinical) {
            Spacer(Modifier.height(8.dp))
            PemaOutlinedButton("Bác sĩ lưu nhận định", onSaveClinical, icon = "save")
        }
        PemaSection("Tư vấn lâm sàng")
        PemaNotice("AI chỉ tạo bản nháp. Bác sĩ cần xem, sửa và xác nhận trước khi lưu vào hồ sơ.")
        PemaTextField(state.transcript, onTranscriptChange, label = "Ghi chú ngắn / transcript mô phỏng", minLines = 2, maxLines = 2)
        if (state.canClinical) {
            PemaPrimary("Tạo bản nháp ghi chú", onGenerateDraft)
        }
        if (state.draft.isNotBlank()) {
            PemaSection("Bản nháp của Pema AI")
            PemaTextField(state.draft, onDraftChange, label = "Chỉnh sửa bản nháp", minLines = 4, maxLines = 6)
            if (state.canClinical) PemaPrimary("Duyệt & lưu vào Patient 360", onApproveDraft)
        }
    }
}

@Composable
internal fun AiBriefRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val staff = session.staffContext()
    val patient = clinic.patient(deps.sessionStore.selectedPatientId())
    var text by rememberSaveable(patient.id) { mutableStateOf(brief(clinic, patient)) }
    val messenger = rememberPemaMessenger()
    val clipboard = LocalClipboardManager.current
    AiBriefScreen(
        state = AiBriefUiState(patient.name, patient.plan, text, canClinical = staff.can("clinical")),
        onTextChange = { text = it },
        onCopy = {
            clipboard.setText(AnnotatedString(text))
            messenger.show("Đã sao chép brief")
        },
        onApprove = {
            runClinicAction(messenger) {
                deps.clinicStore.approveAiBrief(patient.id, text, staff)
                messenger.show("Đã lưu brief có bác sĩ duyệt và nguồn sự kiện")
            }
        },
    )
}

@Composable
internal fun AiBriefScreen(
    state: AiBriefUiState,
    onTextChange: (String) -> Unit,
    onCopy: () -> Unit,
    onApprove: () -> Unit,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.AiBrief)) {
        PemaHero("Brief trước\nbuổi hẹn.", "${state.patientName} · ${state.plan}", "auto_awesome")
        Spacer(Modifier.height(16.dp))
        PemaInfoCard {
            PemaCardTitle("Bản nháp · sửa trước khi duyệt")
            EditableBriefText(state.text, onTextChange)
            Spacer(Modifier.height(8.dp))
            PemaText(
                "Nguồn: Patient 360, sự kiện đã ghi nhận, mục theo dõi đang mở.",
                size = 12f,
                color = PemaColors.Muted,
            )
        }
        PemaOutlinedButton("Sao chép", onCopy, icon = "content_copy")
        if (state.canClinical) PemaPrimary("Duyệt & lưu brief", onApprove)
    }
}

@Composable
private fun EditableBriefText(value: String, onValueChange: (String) -> Unit) {
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        textStyle = PemaType.body,
        cursorBrush = SolidColor(PemaColors.Blue),
        modifier = Modifier.fillMaxWidth().heightIn(min = 84.dp),
    )
}

@Composable
internal fun PlanOverviewRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val patient = clinic.patient(deps.sessionStore.selectedPatientId())
    PlanOverviewScreen(
        state = planOverviewState(patient, session.staffContext()),
        onEdit = { deps.navigator.go(Routes.PlanEdit) },
    )
}

internal fun planOverviewState(patient: ClinicPatient, staff: StaffContext = StaffContext()): PlanOverviewUiState = PlanOverviewUiState(
    plan = patient.plan,
    completed = patient.completed,
    total = patient.total,
    doctor = patient.doctor,
    goal = "Giảm biểu hiện ${patient.concern.lowercase()}, theo dõi đáp ứng qua từng mốc ảnh và bảo đảm người bệnh hiểu chăm sóc tại nhà.",
    milestones = planMilestones(patient.completed, patient.total),
    photoCriterion = "Chính diện · ${patient.completed}/${patient.total}",
    reportedOutcome = "Chưa gửi",
    reminder = if (patient.next != null || patient.crm.recommendationAt != null) "Đang bật" else "Chưa bật",
    canClinical = staff.can("clinical"),
)

internal fun planMilestones(completed: Int, total: Int): List<PlanMilestone> {
    val lastDone = completed.coerceAtLeast(1).coerceAtMost(total.coerceAtLeast(1))
    val rows = mutableListOf<PlanMilestone>()
    if (completed > 0) {
        rows += PlanMilestone("Buổi $lastDone · Đã hoàn tất", "Đã ghi nhận ảnh và hướng dẫn chăm sóc", "check_circle")
    }
    if (completed < total) {
        rows += PlanMilestone("Buổi ${completed + 1} · Tiếp theo", "Cần đánh giá da trước khi thực hiện", "radio_button_checked")
    }
    return rows
}

@Composable
internal fun PlanOverviewScreen(state: PlanOverviewUiState, onEdit: () -> Unit) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PlanOverview)) {
        PemaHero(state.plan, "Kế hoạch đang hoạt động · ${state.completed}/${state.total} buổi · ${state.doctor}", "route")
        Spacer(Modifier.height(16.dp))
        PemaText(state.goal, size = 13f, color = PemaColors.Muted)
        PemaSection("Các mốc")
        state.milestones.forEach { row ->
            PemaTile(row.title, row.sub, row.icon, onClick = null)
        }
        PemaInfoCard {
            PemaCardTitle("Tiêu chí theo dõi")
            PemaCardLine("Ảnh mốc", state.photoCriterion)
            PemaCardLine("Người bệnh tự đánh giá", state.reportedOutcome)
            PemaCardLine("Người duyệt", state.doctor)
            PemaCardLine("Nhắc hẹn", state.reminder)
        }
        PemaNotice("Câu hỏi buổi tới: “Đỏ kéo dài bao lâu sau lần trước? Có thay đổi gì trong chăm sóc tại nhà không?”")
        if (state.canClinical) PemaOutlinedButton("Điều chỉnh kế hoạch", onEdit, icon = "edit")
    }
}

@Composable
internal fun PlanEditRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val staff = session.staffContext()
    val patient = clinic.patient(deps.sessionStore.selectedPatientId())
    var name by rememberSaveable(patient.id) { mutableStateOf(patient.plan) }
    var total by rememberSaveable(patient.id) { mutableStateOf(patient.total.toString()) }
    val messenger = rememberPemaMessenger()
    PlanEditScreen(
        state = PlanEditUiState(name, total, patient.completed, canClinical = staff.can("clinical")),
        onNameChange = { name = it },
        onTotalChange = { total = it },
        onSave = {
            runClinicAction(messenger) {
                deps.clinicStore.updateTreatmentPlan(patient.id, PlanEditInput(name, total.toIntOrNull() ?: -1), staff)
                messenger.show("Đã cập nhật kế hoạch và patient app")
                deps.navigator.back()
            }
        },
    )
}

@Composable
internal fun PlanEditScreen(
    state: PlanEditUiState,
    onNameChange: (String) -> Unit,
    onTotalChange: (String) -> Unit,
    onSave: () -> Unit,
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PlanEdit)) {
        PemaTextField(state.name, onNameChange, label = "Tên kế hoạch")
        Spacer(Modifier.height(14.dp))
        PemaTextField(
            value = state.total,
            onValueChange = onTotalChange,
            label = "Tổng số buổi dự kiến",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        )
        Spacer(Modifier.height(16.dp))
        PemaNotice("Chỉ đổi tên và số buổi dự kiến. Buổi đã ghi nhận không bị sửa.")
        if (state.canClinical) PemaPrimary("Lưu kế hoạch", onSave)
    }
}

@Composable
internal fun SessionRecordRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val session by deps.sessionStore.state.collectAsStateWithLifecycle()
    val staff = session.staffContext()
    val patient = clinic.patient(deps.sessionStore.selectedPatientId())
    var sessionType by rememberSaveable(patient.id) { mutableStateOf(defaultSessionType(patient)) }
    var protocol by rememberSaveable(patient.id) { mutableStateOf(defaultProtocol(patient)) }
    var nextVisit by rememberSaveable(patient.id) { mutableStateOf(addDays(DAY, 30)) }
    var region by rememberSaveable(patient.id) { mutableStateOf("Mặt") }
    var view by rememberSaveable(patient.id) { mutableStateOf("Chính diện") }
    var consent by rememberSaveable(patient.id) { mutableStateOf(patient.photoConsent) }
    var photoPath by rememberSaveable(patient.id) { mutableStateOf<String?>(null) }
    var photoBusy by remember { mutableStateOf(false) }
    var showSource by remember { mutableStateOf(false) }
    val messenger = rememberPemaMessenger()
    val scope = rememberCoroutineScope()
    val camera = deps.platform.camera
    // Read at cleanup time (not captured), so a saved photo is never deleted.
    val pending = remember { PendingPhoto() }
    pending.path = photoPath
    fun replacePhoto(next: CapturedPhoto) {
        photoPath?.takeIf { it != next.path }?.let { old -> scope.launch { camera.discard(CapturedPhoto(old, 0, 0, 0)) } }
        photoPath = next.path
    }
    fun takePhoto(source: suspend () -> CapturedPhoto?) {
        showSource = false
        scope.launch {
            photoBusy = true
            try {
                source()?.let(::replacePhoto)
            } catch (failure: HardwareFailure) {
                messenger.show(failure.message ?: "Không thể lấy ảnh.")
            } finally {
                photoBusy = false
            }
        }
    }
    LaunchedEffect(camera) { camera.recoveredPhotos().collect(::replacePhoto) }
    OnScreenCleared("session-record") {
        pending.path?.let { path -> CoroutineScope(Dispatchers.Default).launch { camera.discard(CapturedPhoto(path, 0, 0, 0)) } }
    }
    SessionRecordScreen(
        state = SessionRecordUiState(
            notice = sessionNotice(patient),
            sessionType = sessionType,
            protocol = protocol,
            nextVisit = nextVisit,
            region = region,
            view = view,
            consent = consent,
            photoSelected = photoPath != null,
            photoPath = photoPath,
            photoBusy = photoBusy,
            canClinical = staff.can("clinical"),
        ),
        onTypeChange = { sessionType = it },
        onProtocolChange = { protocol = it },
        onRegionChange = { region = it },
        onViewChange = { view = it },
        onConsentChange = { consent = it },
        onNextVisitClick = { messenger.show("Chọn ngày tái khám sẽ được nối với bộ chọn lịch.") },
        onAddPhoto = { showSource = true },
        onRetake = { takePhoto { camera.capture() } },
        onPickOther = { takePhoto { camera.pick() } },
        onRemovePhoto = {
            photoPath?.let { old -> scope.launch { camera.discard(CapturedPhoto(old, 0, 0, 0)) } }
            photoPath = null
        },
        onSave = {
            runClinicAction(messenger) {
                deps.clinicStore.recordTreatmentSession(
                    patient.id,
                    TreatmentSessionInput(
                        date = DAY,
                        type = sessionType,
                        note = "Đánh giá trước buổi theo chỉ định bác sĩ.",
                        aftercare = patient.aftercare,
                        region = region,
                        view = view,
                        protocolId = if (protocol.startsWith("Laser CO2")) "laser-co2" else null,
                        nextVisit = nextVisit,
                        hasPhoto = photoPath != null,
                        photoConsent = consent,
                        photoPath = photoPath,
                    ),
                    staff,
                )
                // The photo now belongs to the session record.
                pending.path = null
                photoPath = null
                messenger.show("Đã lưu buổi điều trị và cập nhật hành trình")
                deps.navigator.back()
            }
        },
    )
    if (showSource) {
        PemaPhotoSourceSheet(
            title = "Ảnh mốc · $region · $view",
            onCamera = { takePhoto { camera.capture() } },
            onGallery = { takePhoto { camera.pick() } },
            onDismiss = { showSource = false },
        )
    }
}

/** Unsaved landmark photo of the session form, deleted if the form is closed without saving. */
private class PendingPhoto {
    var path: String? = null
}

internal fun defaultSessionType(patient: ClinicPatient): String =
    if (patient.procedure.isNotBlank()) patient.procedure else sessionTypes.first()

internal fun defaultProtocol(patient: ClinicPatient): String =
    if (patient.procedure.contains("laser", ignoreCase = true)) protocolOptions[1] else protocolOptions[0]

internal fun sessionNotice(patient: ClinicPatient): String {
    val next = minOf(patient.completed + 1, patient.total)
    val alert = if (patient.alerts.isNotEmpty()) {
        "Hồ sơ có cảnh báo: ${patient.alerts.joinToString(", ")}. Xác nhận trước khi thực hiện."
    } else {
        "Kiểm tra phản ứng sau buổi trước, ảnh mốc và hướng dẫn chăm sóc đã gửi."
    }
    return "Buổi $next/${patient.total} · ${patient.doctor}\n$alert"
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun SessionRecordScreen(
    state: SessionRecordUiState,
    onTypeChange: (String) -> Unit,
    onProtocolChange: (String) -> Unit,
    onRegionChange: (String) -> Unit,
    onViewChange: (String) -> Unit,
    onConsentChange: (Boolean) -> Unit,
    onNextVisitClick: () -> Unit,
    onAddPhoto: () -> Unit,
    onSave: () -> Unit,
    onRetake: () -> Unit = {},
    onPickOther: () -> Unit = {},
    onRemovePhoto: () -> Unit = {},
) {
    DetailScaffold(title = Routes.appBarTitleOf(Routes.SessionRecord)) {
        PemaNotice(state.notice)
        PemaDropdownField(state.sessionType, (listOf(state.sessionType) + sessionTypes).distinct(), onTypeChange, label = "Loại buổi")
        Spacer(Modifier.height(14.dp))
        PemaDropdownField(state.protocol, protocolOptions, onProtocolChange, label = "Protocol chăm sóc")
        Spacer(Modifier.height(6.dp))
        PemaTextButton("Tái khám dự kiến ${viDate(state.nextVisit)}", onNextVisitClick, icon = "calendar_month", iconFilled = true)
        PemaChipWrap(Modifier.padding(top = 10.dp, bottom = 8.dp)) {
            regions.forEach { item -> PemaFilterChip(item, selected = state.region == item, onClick = { onRegionChange(item) }) }
        }
        PemaChipWrap(Modifier.padding(bottom = 10.dp)) {
            views.forEach { item -> PemaFilterChip(item, selected = state.view == item, onClick = { onViewChange(item) }) }
        }
        val photoPath = state.photoPath
        if (photoPath != null) {
            LocalPhoto(path = photoPath, height = 220.dp, label = "Ảnh mốc · ${state.region} · ${state.view}")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                PemaTextButton("Chụp lại", onClick = onRetake, icon = "refresh", enabled = !state.photoBusy)
                PemaTextButton("Chọn ảnh khác", onClick = onPickOther, icon = "photo_library", enabled = !state.photoBusy)
                PemaTextButton("Bỏ ảnh", onClick = onRemovePhoto, icon = "delete", enabled = !state.photoBusy)
            }
        } else {
            PemaOutlinedButton(
                if (state.photoBusy) "Đang lấy ảnh…" else if (state.photoSelected) "Đã chọn ảnh mốc" else "Thêm ảnh mốc",
                onAddPhoto,
                icon = "add_a_photo",
                enabled = !state.photoBusy,
            )
        }
        PemaCheckRow("Người bệnh đã đồng ý dùng ảnh chăm sóc", state.consent, onConsentChange)
        if (state.canClinical) PemaPrimary("Lưu buổi điều trị", onSave)
    }
}

private fun runClinicAction(messenger: com.pema.clinic.core.ui.widgets.PemaMessenger, block: () -> Unit) {
    try {
        block()
    } catch (error: ClinicError) {
        messenger.show(error.message ?: "Không thể thực hiện")
    }
}
