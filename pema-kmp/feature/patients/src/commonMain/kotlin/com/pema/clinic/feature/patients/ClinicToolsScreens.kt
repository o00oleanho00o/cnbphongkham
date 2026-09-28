package com.pema.clinic.feature.patients

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
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
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaIcon
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaSearchField
import com.pema.clinic.core.ui.widgets.PemaText
import com.pema.clinic.core.ui.widgets.PemaTextField
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.Catalog
import com.pema.clinic.shared.catalog.MutableCatalogRepository
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.clinic.ClinicError
import com.pema.clinic.shared.clinic.ClinicPatient
import com.pema.clinic.shared.clinic.ClinicState
import com.pema.clinic.shared.clinic.DAY
import com.pema.clinic.shared.clinic.NewClinicPatientInput
import com.pema.clinic.shared.clinic.createPatient
import com.pema.clinic.shared.clinic.daysBetween
import com.pema.clinic.shared.clinic.patient
import kotlinx.coroutines.launch

fun NavGraphBuilder.clinicToolsGraph(deps: FeatureDeps) {
    composable(Routes.NewPatient) { NewPatientRoute(deps) }
    composable(Routes.PhotoStudio) { PhotoStudioRoute(deps) }
    composable(Routes.AskQuery) { AskQueryRoute(deps) }
}

@Immutable
internal data class NewPatientUiState(
    val name: String = "",
    val age: String = "",
    val concern: String = "",
) {
    val canCreate: Boolean get() = name.trim().isNotEmpty()
}

@Composable
internal fun NewPatientRoute(deps: FeatureDeps) {
    var name by rememberSaveable { mutableStateOf("") }
    var age by rememberSaveable { mutableStateOf("") }
    var concern by rememberSaveable { mutableStateOf("") }
    val state = NewPatientUiState(name, age, concern)
    val messenger = rememberPemaMessenger()
    DetailScaffold(title = Routes.appBarTitleOf(Routes.NewPatient)) {
        NewPatientScreen(
            state = state,
            onChange = {
                name = it.name
                age = it.age
                concern = it.concern
            },
            onCreate = {
                try {
                    val patient = deps.clinicStore.createPatient(
                        NewClinicPatientInput(state.name, state.age, state.concern),
                    )
                    val synced = syncNewClinicPatientToCatalog(deps, patient)
                    selectPatientInCatalog(deps, patient.id)
                    messenger.show(if (synced) "Đã tạo hồ sơ demo" else "Đã tạo hồ sơ trong ClinicStore; cần đồng bộ catalog để hiện trong tìm kiếm")
                    deps.navigator.go(Routes.Patient360)
                } catch (error: ClinicError) {
                    messenger.show(error.message ?: "Không thể tạo hồ sơ")
                }
            },
        )
    }
}

@Composable
internal fun NewPatientScreen(
    state: NewPatientUiState,
    onChange: (NewPatientUiState) -> Unit,
    onCreate: () -> Unit,
) {
    PemaNotice("Hồ sơ demo · tìm theo tên, mã hoặc số điện thoại trước khi tạo mới.")
    PemaTextField(
        value = state.name,
        onValueChange = { onChange(state.copy(name = it)) },
        label = "Họ và tên",
    )
    Spacer(Modifier.height(14.dp))
    PemaTextField(
        value = state.age,
        onValueChange = { onChange(state.copy(age = it)) },
        label = "Tuổi",
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
    )
    Spacer(Modifier.height(14.dp))
    PemaTextField(
        value = state.concern,
        onValueChange = { onChange(state.copy(concern = it)) },
        label = "Mối quan tâm",
    )
    Spacer(Modifier.height(8.dp))
    PemaPrimary("Tạo hồ sơ", onCreate)
}

@Immutable
internal data class PhotoStudioUiState(
    val patientId: String,
    val name: String,
    val concern: String,
    val view: String = "Chính diện",
    val sliderMode: Boolean = false,
    val photoConsent: Boolean = true,
    val latestSessionId: String = "minh họa",
    val region: String = "Mặt",
) {
    val metadata: String
        get() = "Metadata: vùng $region · góc $view · đồng ý chăm sóc: ${if (photoConsent) "có ghi nhận" else "chưa xác nhận"}"
}

internal val photoStudioViews = listOf("Chính diện", "Má trái", "Má phải")

internal fun photoStudioState(patient: ClinicPatient, view: String = "Chính diện", sliderMode: Boolean = false): PhotoStudioUiState {
    val latest = patient.sessions.lastOrNull { it.view.isBlank() || it.view == view }
    return PhotoStudioUiState(
        patientId = patient.id,
        name = patient.name,
        concern = patient.concern,
        view = view,
        sliderMode = sliderMode,
        photoConsent = patient.photoConsent,
        latestSessionId = latest?.id ?: "minh họa",
        region = latest?.region?.ifBlank { "Mặt" } ?: "Mặt",
    )
}

@Composable
internal fun PhotoStudioRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    val patientId = deps.sessionStore.selectedPatientId()
    var view by rememberSaveable { mutableStateOf("Chính diện") }
    var sliderMode by rememberSaveable { mutableStateOf(false) }
    val state = photoStudioState(clinic.patient(patientId), view, sliderMode)
    val messenger = rememberPemaMessenger()
    val scope = rememberCoroutineScope()
    DetailScaffold(title = Routes.appBarTitleOf(Routes.PhotoStudio)) {
        PhotoStudioScreen(
            state = state,
            onViewChange = { view = it },
            onToggleCompare = { sliderMode = !sliderMode },
            onAddPhoto = {
                scope.launch {
                    messenger.show("Gắn ảnh với buổi điều trị và đồng ý ảnh")
                    deps.navigator.go(Routes.ProgressPhotos)
                }
            },
        )
    }
}

@Composable
internal fun PhotoStudioScreen(
    state: PhotoStudioUiState,
    onViewChange: (String) -> Unit,
    onToggleCompare: () -> Unit,
    onAddPhoto: () -> Unit,
) {
    PemaHeading("Before / After Studio", "${state.name} · ${state.concern}")
    PemaChipWrap(Modifier.padding(bottom = 16.dp)) {
        photoStudioViews.forEach { label ->
            PemaFilterChip(label, selected = state.view == label, onClick = { onViewChange(label) })
        }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        StudioPhotoPanel("Trước")
        StudioPhotoPanel("Sau")
    }
    Spacer(Modifier.height(12.dp))
    PemaNotice(
        "Chưa kiểm định căn chỉnh ảnh; bác sĩ kiểm tra điều kiện chụp trước khi so sánh. " +
            "Không suy ra hiệu quả y khoa từ ảnh minh họa.",
    )
    PemaText(state.metadata, size = 12f, color = PemaColors.Muted)
    Spacer(Modifier.height(12.dp))
    PemaOutlinedButton(
        text = if (state.sliderMode) "Đặt cạnh nhau" else "So sánh trượt",
        onClick = onToggleCompare,
        icon = "compare",
    )
    PemaPrimary("Thêm ảnh", onAddPhoto)
}

@Composable
private fun RowScope.StudioPhotoPanel(label: String) {
    Column(
        Modifier
            .weight(1f)
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

@Immutable
internal data class AskQueryUiState(
    val query: String = "",
    val selectedPreset: String? = AskPreset.Image.label,
    val result: AskQueryResult,
)

@Immutable
internal data class AskQueryResult(
    val answer: String,
    val method: String,
    val rows: List<AskQueryRow>,
    val source: String,
    val route: String,
)

@Immutable
internal data class AskQueryRow(
    val patientId: String,
    val patientName: String,
    val detail: String,
    val icon: String,
)

internal enum class AskPreset(val label: String, val question: String) {
    Image("Ảnh chờ xem", "Ai có ảnh gửi sau laser đang chờ xem?"),
    Plans("Kế hoạch đang chạy", "Có bao nhiêu kế hoạch đang chạy?"),
    Overdue("Quá hạn tái khám", "Ai quá hạn tái khám hơn 30 ngày?"),
}

internal fun askQueryState(clinic: ClinicState, query: String = "", selectedPreset: String? = AskPreset.Image.label): AskQueryUiState {
    val question = query.trim().ifEmpty {
        AskPreset.entries.firstOrNull { it.label == selectedPreset }?.question.orEmpty()
    }
    return AskQueryUiState(query, selectedPreset, askPema(question, clinic))
}

internal fun askPema(question: String, state: ClinicState): AskQueryResult {
    val q = question.trim()
    val unsupported = AskQueryResult(
        answer = "Demo hỗ trợ 3 nhóm câu hỏi: ảnh chờ xem, kế hoạch chưa hoàn tất, và lần điều trị gần nhất hơn 30 ngày.",
        method = "Chọn câu gợi ý để có kết quả kiểm tra được.",
        rows = emptyList(),
        source = "Nguồn: dữ liệu demo · kiểm tra lại trước khi dùng.",
        route = Routes.Patient360,
    )
    if (q.isEmpty()) return unsupported

    var result = unsupported
    if (Regex("kế hoạch|plan", RegexOption.IGNORE_CASE).containsMatchIn(q)) {
        val rows = state.patients.filter { it.completed < it.total }
        result = AskQueryResult(
            answer = "Có ${rows.size} kế hoạch chưa hoàn tất trong ${state.patients.size} hồ sơ demo.",
            method = "Cách tính: Patient 360, completed < total.",
            rows = rows.take(4).map {
                AskQueryRow(it.id, it.name, "${it.completed}/${it.total} buổi · ${it.plan}", "route")
            },
            source = "Nguồn: Patient 360 · kiểm tra lại trước khi dùng.",
            route = Routes.Patient360,
        )
    }
    if (Regex("ảnh|photo|laser", RegexOption.IGNORE_CASE).containsMatchIn(q)) {
        val rows = state.followups.filter { it.status == "open" && it.image != null }
        result = AskQueryResult(
            answer = "${rows.size} ảnh chờ bác sĩ xem",
            method = "Cách tính: mục Theo dõi loại Ảnh, trạng thái đang mở.",
            rows = rows.map { followUp ->
                val patient = state.patient(followUp.patient)
                AskQueryRow(
                    patient.id,
                    patient.name,
                    "${followUp.type} · ${shortDate(followUp.date)}",
                    "photo_camera",
                )
            },
            source = "Nguồn: Follow-up Inbox · kiểm tra lại trước khi dùng.",
            route = Routes.FollowUpInbox,
        )
    } else if (Regex("quá hạn|30 ngày", RegexOption.IGNORE_CASE).containsMatchIn(q)) {
        val rows = state.patients.filter { patient ->
            val lastVisit = patient.lastVisit
            lastVisit != null && daysBetween(lastVisit) > 30
        }
        result = AskQueryResult(
            answer = "Có ${rows.size} hồ sơ có lần điều trị gần nhất hơn 30 ngày.",
            method = "Cách tính: lastVisit, mốc demo ${shortDate(DAY)}; đây là bộ lọc cần xem xét, không tự động là trễ hẹn.",
            rows = rows.take(4).map {
                AskQueryRow(it.id, it.name, "${it.id} · lần gần nhất ${shortDate(it.lastVisit ?: DAY)}", "schedule")
            },
            source = "Nguồn: Patient 360 · kiểm tra lại trước khi dùng.",
            route = Routes.Patient360,
        )
    }
    return result
}

@Composable
internal fun AskQueryRoute(deps: FeatureDeps) {
    val clinic by deps.clinicStore.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") }
    var preset by rememberSaveable { mutableStateOf<String?>(AskPreset.Image.label) }
    val state = askQueryState(clinic, query, preset)
    DetailScaffold(title = Routes.appBarTitleOf(Routes.AskQuery)) {
        AskQueryScreen(
            state = state,
            onQueryChange = {
                query = it
                preset = null
            },
            onPreset = {
                preset = it.label
                query = ""
            },
            onOpenPatient = { id ->
                selectPatientInCatalog(deps, id)
                deps.navigator.go(Routes.Patient360)
            },
        )
    }
}

@Composable
internal fun AskQueryScreen(
    state: AskQueryUiState,
    onQueryChange: (String) -> Unit,
    onPreset: (AskPreset) -> Unit,
    onOpenPatient: (String) -> Unit,
) {
    PemaHeading("Ask Pema", "Truy vấn mô phỏng · chưa tích hợp mô hình AI")
    PemaSearchField(
        value = state.query,
        onValueChange = onQueryChange,
        hint = "Bạn muốn biết điều gì?",
    )
    Spacer(Modifier.height(16.dp))
    PemaChipWrap(Modifier.padding(bottom = 16.dp)) {
        AskPreset.entries.forEach { preset ->
            PemaFilterChip(
                label = preset.label,
                selected = state.selectedPreset == preset.label,
                onClick = { onPreset(preset) },
            )
        }
    }
    PemaNotice("${state.result.answer}\n${state.result.method}")
    state.result.rows.forEach { row ->
        PemaTile(
            title = row.patientName,
            sub = row.detail,
            icon = row.icon,
            onClick = { onOpenPatient(row.patientId) },
        )
    }
    PemaText(state.result.source, size = 12f, color = PemaColors.Muted)
}

private fun syncNewClinicPatientToCatalog(deps: FeatureDeps, patient: ClinicPatient): Boolean {
    val mutable = deps.catalogRepository as? MutableCatalogRepository ?: return false
    val catalog = mutable.catalog()
    if (catalog.profiles.any { it.id == patient.id }) return true
    mutable.replace(
        Catalog(
            products = catalog.products,
            profiles = catalog.profiles + PatientProfile(
                id = patient.id,
                name = patient.name,
                doctor = patient.doctor,
                sessions = patient.completed,
                totalSessions = patient.total,
                appointment = patient.time,
                day = patient.next ?: "",
                careGroup = "",
                caseLabel = "",
            ),
        ),
    )
    return true
}

private fun selectPatientInCatalog(deps: FeatureDeps, patientId: String) {
    val index = deps.catalogRepository.catalog().profiles.indexOfFirst { it.id == patientId }
    if (index >= 0) deps.sessionStore.select(index)
}

internal fun shortDate(value: String): String {
    val date = value.take(10)
    val parts = date.split("-")
    if (parts.size != 3) return value
    return "${parts[2].toIntOrNull() ?: parts[2]}/${parts[1].toIntOrNull() ?: parts[1]}/${parts[0]}"
}
