package com.pema.clinic.feature.schedule

import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDefaults
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.pema.clinic.core.common.Routes
import com.pema.clinic.core.ui.theme.PemaColors
import com.pema.clinic.core.ui.widgets.DetailScaffold
import com.pema.clinic.core.ui.widgets.LocalOnBack
import com.pema.clinic.core.ui.widgets.rememberPemaMessenger
import com.pema.clinic.core.ui.widgets.PemaFilterChip
import com.pema.clinic.core.ui.widgets.PemaHeading
import com.pema.clinic.core.ui.widgets.PemaHero
import com.pema.clinic.core.ui.widgets.PemaNotice
import com.pema.clinic.core.ui.widgets.PemaOutlinedButton
import com.pema.clinic.core.ui.widgets.PemaPrimary
import com.pema.clinic.core.ui.widgets.PemaTextButton
import com.pema.clinic.core.ui.widgets.PemaTile
import com.pema.clinic.core.ui.widgets.PemaChipWrap
import com.pema.clinic.core.ui.widgets.PemaSection
import com.pema.clinic.core.ui.widgets.WeekStrip
import com.pema.clinic.shared.FeatureDeps
import com.pema.clinic.shared.catalog.PatientProfile
import com.pema.clinic.shared.patients.PatientState
import com.pema.clinic.shared.session.Session
import kotlinx.coroutines.flow.StateFlow
import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.atStartOfDayIn
import kotlinx.datetime.toLocalDateTime

fun NavGraphBuilder.scheduleGraph(deps: FeatureDeps) {
    composable(Routes.Booking) {
        val vm = viewModel { BookingViewModel(deps) }
        BookingRoute(vm)
    }
    composable(Routes.AppointmentDetail) {
        val vm = viewModel { AppointmentViewModel(deps, Routes.AppointmentDetail) }
        AppointmentRoute(vm)
    }
    composable(Routes.MyAppointments) {
        val vm = viewModel { AppointmentViewModel(deps, Routes.MyAppointments) }
        AppointmentRoute(vm)
    }
    composable(Routes.Services) {
        ServicesScreen(
            onServiceClick = { deps.navigator.go(Routes.Booking) },
            onEditService = { index: Int ->
                deps.navigator.go(Routes.withArgs(Routes.ServiceEdit, "id" to "S$index"))
            }.takeIf { deps.sessionStore.state.value.allows(Routes.ServiceEdit) },
        )
    }
    composable(Routes.Resources) {
        ResourcesScreen(
            onResourceClick = { deps.navigator.go(Routes.Booking) },
            onBlockRoom = { deps.navigator.go(Routes.RoomBlock) }.takeIf { deps.sessionStore.state.value.allows(Routes.RoomBlock) },
        )
    }
}

internal class BookingViewModel(private val deps: FeatureDeps) : ViewModel() {
    val session: StateFlow<Session> = deps.sessionStore.state
    val patients: StateFlow<Map<String, PatientState>> = deps.patientsStore.state

    fun state(session: Session = this.session.value, patients: Map<String, PatientState> = this.patients.value): BookingUiState {
        val (profile, patient) = deps.currentPatient(session, patients)
        return BookingUiState(
            patientName = profile.name,
            day = patient.day,
            appointment = patient.appointment,
            confirmed = patient.confirmed,
        )
    }

    fun chooseDay(day: String) = updateCurrentPatient { it.copy(day = day) }

    fun chooseSlot(slot: String) {
        if (slot != blockedBookingSlot) updateCurrentPatient { it.copy(appointment = slot) }
    }

    fun confirm(): String {
        val id = deps.sessionStore.selectedPatientId()
        val patient = deps.patientsStore.of(id)
        deps.patientsStore.update(id) { it.copy(confirmed = true) }
        deps.navigator.back()
        return "Đã lưu lịch ${patient.appointment} · ${patient.day}"
    }

    private fun updateCurrentPatient(change: (PatientState) -> PatientState) {
        deps.patientsStore.update(deps.sessionStore.selectedPatientId(), change)
    }
}

internal class AppointmentViewModel(
    private val deps: FeatureDeps,
    private val route: String,
) : ViewModel() {
    val title: String = Routes.titleOf(route)
    val session: StateFlow<Session> = deps.sessionStore.state
    val patients: StateFlow<Map<String, PatientState>> = deps.patientsStore.state

    fun state(session: Session = this.session.value, patients: Map<String, PatientState> = this.patients.value): AppointmentUiState {
        val (profile, patient) = deps.currentPatient(session, patients)
        return AppointmentUiState(
            title = title,
            patientName = profile.name,
            appointment = patient.appointment,
            day = patient.day,
            confirmed = patient.confirmed,
            showClinicActions = route == Routes.AppointmentDetail && !session.careMode,
        )
    }

    fun confirmAttendance() = updateCurrentPatient { it.copy(confirmed = true) }

    fun reschedule() {
        deps.navigator.go(Routes.Booking)
    }

    fun openPatient360() {
        deps.navigator.go(Routes.Patient360)
    }

    private fun updateCurrentPatient(change: (PatientState) -> PatientState) {
        deps.patientsStore.update(deps.sessionStore.selectedPatientId(), change)
    }
}

@Immutable
internal data class BookingUiState(
    val title: String = Routes.titleOf(Routes.Booking),
    val patientName: String,
    val day: String,
    val appointment: String,
    val confirmed: Boolean,
    val slots: List<String> = bookingSlots,
)

@Immutable
internal data class AppointmentUiState(
    val title: String,
    val patientName: String,
    val appointment: String,
    val day: String,
    val confirmed: Boolean,
    val showClinicActions: Boolean,
) {
    val heroTitle: String get() = if (day.isEmpty()) "Chưa có lịch hẹn" else "$appointment · $day"
    val confirmText: String get() = if (confirmed) "Đã xác nhận" else "Xác nhận tham dự"
    val confirmEnabled: Boolean get() = !confirmed && day.isNotEmpty()
}

@Immutable
internal data class ScheduleService(val name: String, val description: String)

@Immutable
internal data class ScheduleResource(val name: String, val hours: String)

internal val scheduleServices = listOf(
    ScheduleService("Tái khám & đánh giá", "300.000 ₫ · 30 phút"),
    ScheduleService("Tư vấn da liễu", "500.000 ₫ · 45 phút"),
    ScheduleService("Laser theo chỉ định", "2.500.000 ₫ · 45 + 15 phút"),
    ScheduleService("Chăm sóc theo chỉ định", "1.200.000 ₫ · 45 + 15 phút"),
)

internal val scheduleResources = listOf(
    ScheduleResource("BS. Tâm", "08:00–18:00 · Nghỉ 12:00–13:00"),
    ScheduleResource("BS. Mai", "08:00–18:00 · Nghỉ 12:00–13:00"),
    ScheduleResource("BS. An", "08:00–18:00 · Nghỉ 12:00–13:00"),
    ScheduleResource("BS. Lan", "08:00–18:00 · Nghỉ 12:00–13:00"),
)

internal val bookingSlots = listOf("09:00", "10:30", "11:00", "14:00", "15:30")
internal const val blockedBookingSlot = "09:00"

@Composable
private fun BookingRoute(vm: BookingViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val patients by vm.patients.collectAsStateWithLifecycle()
    val messenger = rememberPemaMessenger()
    BookingScreen(
        state = vm.state(session, patients),
        onDayPicked = vm::chooseDay,
        onSlotClick = vm::chooseSlot,
        onConfirm = { messenger.show(vm.confirm()) },
    )
}

@Composable
private fun AppointmentRoute(vm: AppointmentViewModel) {
    val session by vm.session.collectAsStateWithLifecycle()
    val patients by vm.patients.collectAsStateWithLifecycle()
    AppointmentScreen(
        state = vm.state(session, patients),
        onConfirmAttendance = vm::confirmAttendance,
        onReschedule = vm::reschedule,
        onOpenPatient360 = vm::openPatient360,
    )
}

@Composable
internal fun BookingScreen(
    state: BookingUiState,
    onDayPicked: (String) -> Unit,
    onSlotClick: (String) -> Unit,
    onConfirm: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    var showDatePicker by remember { mutableStateOf(false) }
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaHeading(state.patientName, "Chọn ngày và giờ trước khi xác nhận")
        WeekStrip()
        PemaTile(
            title = state.day,
            sub = "Chạm để đổi ngày",
            icon = "calendar_today",
            onClick = { showDatePicker = true },
        )
        PemaNotice("BS. Tâm · Khám da liễu · 30 phút\n09:00 đã có lịch, không thể chọn.")
        PemaChipWrap {
            state.slots.forEach { slot ->
                PemaFilterChip(
                    label = slot,
                    selected = state.appointment == slot,
                    enabled = slot != blockedBookingSlot,
                    onClick = { onSlotClick(slot) },
                )
            }
        }
        PemaPrimary("Xác nhận lịch", onClick = onConfirm)
    }
    if (showDatePicker) {
        BookingDatePickerDialog(
            onDismiss = { showDatePicker = false },
            onPicked = { day ->
                showDatePicker = false
                onDayPicked(day)
            },
        )
    }
}

@Composable
internal fun AppointmentScreen(
    state: AppointmentUiState,
    onConfirmAttendance: () -> Unit,
    onReschedule: () -> Unit,
    onOpenPatient360: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
) {
    DetailScaffold(title = state.title, onBack = onBack) {
        PemaHero(state.heroTitle, "BS. Tâm · Khám da liễu", "calendar_month")
        PemaSection(state.patientName)
        PemaNotice("Tái khám & đánh giá · 30 phút")
        PemaPrimary(state.confirmText, onClick = if (state.confirmEnabled) onConfirmAttendance else null)
        if (state.showClinicActions) {
            PemaPrimary("Dời lịch", onClick = onReschedule)
            PemaPrimary("Mở Patient 360", onClick = onOpenPatient360)
        }
    }
}

@Composable
internal fun ServicesScreen(
    onServiceClick: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
    /** Web "Chỉnh dịch vụ" (canvas I9) for service S<index>; null hides it (Flutter F13 has none). */
    onEditService: ((Int) -> Unit)? = null,
) {
    DetailScaffold(title = Routes.titleOf(Routes.Services), onBack = onBack) {
        PemaHeading("Danh mục dịch vụ", "Giá và thời lượng tham khảo như web")
        scheduleServices.forEach { service ->
            PemaTile(
                title = service.name,
                sub = service.description,
                icon = "spa",
                onClick = onServiceClick,
            )
        }
        if (onEditService != null) {
            PemaSection("Chỉnh dịch vụ")
            scheduleServices.forEachIndexed { index, service ->
                PemaTile(service.name, "Thời lượng, giá, trạng thái · áp dụng cho lịch mới", "edit", { onEditService(index) })
            }
        }
    }
}

@Composable
internal fun ResourcesScreen(
    onResourceClick: () -> Unit,
    onBack: (() -> Unit)? = LocalOnBack.current,
    /** Web "Khóa thời gian phòng" (canvas I8); null hides it (Flutter F14 has none). */
    onBlockRoom: (() -> Unit)? = null,
) {
    DetailScaffold(title = Routes.titleOf(Routes.Resources), onBack = onBack) {
        PemaHeading("Nguồn lực phòng khám", "Chạm lịch để điều phối theo ca")
        scheduleResources.forEach { resource ->
            PemaTile(
                title = resource.name,
                sub = resource.hours,
                icon = "medical_services",
                onClick = onResourceClick,
            )
        }
        PemaNotice("Laser & thủ thuật · Bảo trì 14:00–15:00 ngày 23/09. Khóa phòng phức tạp duyệt ở web.")
        if (onBlockRoom != null) {
            PemaOutlinedButton("Khóa thời gian phòng", onClick = onBlockRoom, icon = "block")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BookingDatePickerDialog(
    onDismiss: () -> Unit,
    onPicked: (String) -> Unit,
) {
    val state = rememberDatePickerState(
        initialSelectedDateMillis = bookingInitialDateMillis,
        yearRange = 2026..2027,
        selectableDates = bookingSelectableDates,
    )
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            PemaTextButton(
                text = "OK",
                enabled = state.selectedDateMillis != null,
                onClick = { state.selectedDateMillis?.let { onPicked(formatPickedDay(it)) } },
            )
        },
        dismissButton = { PemaTextButton("Hủy", onClick = onDismiss) },
    ) {
        DatePicker(
            state = state,
            colors = DatePickerDefaults.colors(
                selectedDayContainerColor = PemaColors.Blue,
                todayDateBorderColor = PemaColors.Blue,
                todayContentColor = PemaColors.Blue,
            ),
        )
    }
}

private fun FeatureDeps.currentPatient(
    session: Session,
    patients: Map<String, PatientState>,
): Pair<PatientProfile, PatientState> {
    val catalog = catalogRepository.catalog()
    val profile = catalog.profiles.getOrElse(session.selected.coerceIn(0, catalog.profiles.lastIndex)) { catalog.profiles.first() }
    return profile to (patients[profile.id] ?: patientsStore.of(profile.id))
}

private val bookingInitialDateMillis = localDateMillis(2026, 9, 22)
private val bookingFirstDateMillis = localDateMillis(2026, 9, 22)
private val bookingLastDateMillis = localDateMillis(2027, 1, 1)

@OptIn(ExperimentalMaterial3Api::class)
private val bookingSelectableDates = object : SelectableDates {
    override fun isSelectableDate(utcTimeMillis: Long): Boolean = utcTimeMillis in bookingFirstDateMillis..bookingLastDateMillis
    override fun isSelectableYear(year: Int): Boolean = year in 2026..2027
}

private fun localDateMillis(year: Int, month: Int, day: Int): Long =
    LocalDate(year, month, day).atStartOfDayIn(TimeZone.UTC).toEpochMilliseconds()

internal fun formatPickedDay(utcTimeMillis: Long): String {
    val date = Instant.fromEpochMilliseconds(utcTimeMillis).toLocalDateTime(TimeZone.UTC).date
    return "${date.dayOfMonth}/${date.monthNumber}/${date.year}"
}
